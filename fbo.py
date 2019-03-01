'''
This code uses the FBO Scraper GSA code and builds functionality on top of it
The goal is to use the daily API pseudo-XML and the links it includes to each page
In order to get info on all of the solicitations and awards from the DoD
'''

import os

my_dir=r'C:\Users\admin\Anaconda3\pkgs\fbo-scraper'
my_dir='.'
os.chdir(my_dir)

import sys
from datetime import datetime, timedelta
import json
import pandas as pd
import re
import numpy as np
from bs4 import BeautifulSoup
from urllib.request import urlopen
import fbo_nightly_scraper
from pytz import timezone
pd.set_option('mode.chained_assignment', None)
print("Packages read.")

import boto3
ses_client = boto3.client('ses')
s3_client = boto3.client('s3')


def get_nightly_data(date, notice_types, naics):
    status=False
    while status==False:
        try:
            nfbo = fbo_nightly_scraper.NightlyFBONotices(date = date, notice_types = notice_types, naics = naics)
            file_lines = nfbo.download_from_ftp()
            if not file_lines:
                #exit program if download_from_ftp() failed
                sys.exit(1)
            json_str = nfbo.pseudo_xml_to_json(file_lines)
            nightly_data = json.loads(json_str)
            status=True
            return nightly_data
        except:
            pass

def parameters_of_request(date):    
    #notice_types= ['MOD','PRESOL','COMBINE', 'AMDCSS']
    notice_types=['PRESOL','SRCSGT','SNOTE','SSALE','COMBINE','AMDCSS',
                        'MOD','AWARD','JA','FAIROPP','ARCHIVE','UNARCHIVE',
                        'ITB','FSTD','EPSUPLOAD','DELETE']
    naics = ['334111', '334118', '3343', '33451', '334516', '334614', '5112', '518', 
             '54169', '54121', '5415', '54169', '61142']
    nightly_data = get_nightly_data(date, notice_types, naics)
    return(nightly_data)

def convert_dict_to_df(date):
    data=parameters_of_request(date)
    list_of_keys=data.keys()
    df=pd.DataFrame()
    for i in list_of_keys:
        df=pd.concat([df,pd.DataFrame.from_dict(data[i])])
    return(df)
    
def grab_date_range(number_of_days):
    eastern = timezone('US/Eastern')
    df=pd.DataFrame()
    for number in range(0, number_of_days):
        date_we_want = datetime.now().astimezone(eastern) - timedelta(number+1)
        date = date_we_want.strftime("%Y%m%d")
        new_df=convert_dict_to_df(date)
        df=pd.concat([df, new_df])  
    return(df)

def filter_by_real(df, column):
    return(df.dropna(subset=[column]))

def filter_by_agency(df):
    dod_agencies=["department of the navy", "department of the army", 
                  "other defense agencies", "department of the air force"]
    filtered_df=df[df['agency'].str.lower().isin(dod_agencies)]
    return(filtered_df)
    
def cleanhtml(raw_html):
  cleanr = re.compile('<.*?>')
  cleantext = re.sub(cleanr, '', raw_html)
  cleantext=cleantext.replace(r"&nbsp;", "  ")
  return cleantext

def clean_column_names(df):
    crosswalk_of_columns={"subject": "Solicitation Name",
                      "agency": "Agency",
                      "office": "Office",
                      "contact": "Primary POC",
                      "office": "Office",
                      "solnbr": "Solicitation Number",
                      "ntype": "Notice Type",
                      "date": "Posted Date",
                      "respdate": "Bad Response Date",
                      "setaside": "Set Aside",
                      "classcod": "Classification Code",
                      "naics": "NAICS Code",
                      "url": "Link",
                      "awdamt": "Award Amount",
                      "awddate": "Award Date",
                      "awdnbr": "Award Number",
                      "awardee": "Awardee",
                      "desc": "Description",
                      "email": "Email"}
    return(df.rename(columns = crosswalk_of_columns))
    
def gen_var_with_in_string(df, column, word, newcolumn):
    df[newcolumn] = np.where(df[column].str.contains(word), 'Present', 'Absent')
    return(df)

def extract_digits(my_string):
    try:
        return((''.join(filter(str.isdigit, my_string))))
    except:
        return(my_string)

def extract_alphanumeric(my_string):
    try:
        my_string=re.sub(r'\W+', '', my_string)
        return(my_string)
    except:
        return(str(my_string))

def read_merge_naics_descriptions(df):
    df['NAICS Code']=df['NAICS Code'].apply(extract_digits)
    df['NAICS Code']=pd.to_numeric(df['NAICS Code'])
    naics_codes=pd.read_excel(sys.argv[1])
    merged_df=df.merge(naics_codes, left_on='NAICS Code', right_on='CodeNumber', how='left' )
    return(merged_df)
    
def read_merge_procurement_codes(df):
    procurement_codes=pd.read_excel(sys.argv[2])
    procurement_codes['ProcurementCode']=procurement_codes['ProcurementCode'].apply(extract_alphanumeric)
    merged_df=df.merge(procurement_codes, left_on='Classification Code', right_on='ProcurementCode', how='left' )
    return(merged_df)

def try_link(link):
    try:
        #there was a bug with extra spaces, which is why I' using urllib instead of requests
        html = urlopen(link)
        data=(html.read())
        soup = BeautifulSoup(data, "lxml")
        return(soup)
    except:
        return("Link Down")

def get_id_field_from_soup(output, link, IdString):
    if output!="Link Down":
        div= output.find("div", {"id": IdString})
        if div:
            Posted_Date = div.contents[0].replace("\n","").replace("\t","")
            return(Posted_Date)
        else:
            return("")
    else:
        return(output)

def get_original_posted_date_and_original_response_deadline(link):
    output=try_link(link)
    original_posted_date=get_id_field_from_soup(output, link, "dnf_class_values_procurement_notice__original_posted_date__widget")
    original_response_deadline=get_id_field_from_soup(output, link, "dnf_class_values_procurement_notice__original_response_deadline__widget")
    notice_type=get_id_field_from_soup(output, link,"dnf_class_values_procurement_notice__procurement_type__widget")
    response_date=get_id_field_from_soup(output, link, "dnf_class_values_procurement_notice__response_deadline__widget")
    print(f"I scraped {link} and all I got was this log message.")
    return([notice_type, original_posted_date, original_response_deadline, response_date])


def get_fields_from_scraping(df):
    #this works but takes forever; would be good to work on that
    #df[['Notice Type', 'Original Posted Date','Original Response Date', 'Response Date']]=df['Link'].swifter.apply(get_original_posted_date_and_original_response_deadline).apply(pd.Series)
    df[['Notice Type', 'Original Posted Date','Original Response Date', 'Response Date']]=df['Link'].apply(get_original_posted_date_and_original_response_deadline).apply(pd.Series)
    return(df)
    

def clean_dates(df):
    df['Posted Date']=df['Posted Date'].str[0:2]+"/"+df['Posted Date'].str[2:4]+"/20"+df['year']
    #df['Response Date']=df['Response Date'].str[0:2]+"/"+df['Response Date'].str[2:4]+"/20"+df['Response Date'].str[4:6]
    #df['Award Date']=df['Award Date'].str[0:2]+"/"+df['Award Date'].str[2:4]+"/20"+df['Award Date'].str[4:6]
    return(df)
    
def clean_up_and_output(df):    
    #let's make this all pretty
    FileName=datetime.now().strftime('%b-%d-%Y')+"_Output.xlsx"
    columns_to_keep=['Solicitation Name', 'Description', 'Classification Code','NAICS Code', 
                     'Train in Desc', 'Train in SolName', 'Agency', 'Office', 'Notice Type', 
                     'Solicitation Number', 'Award Number', 'Award Date',
                     'Award Amount','Awardee','Set Aside','Posted Date','Response Date', 
                     'Link', 'Email','Primary POC', 'CodeDescription', 'Original Posted Date', "ProcurementDescription",
                     'Original Response Date']
    df_for_output=clean_dates(df)
    df_for_output=df_for_output[columns_to_keep]
    writer = pd.ExcelWriter(sys.argv[3]+ FileName, engine='xlsxwriter')    
    df_for_output.to_excel(writer,'FBO')
    writer.save()
    return(FileName)

def send_email(FileName):
    #at some point we'll want email addresses to be not hard-coded in the function
    response = ses_client.send_email(
            Source='abigailhaddad@abigailhaddad.com',
            Destination={
                'ToAddresses': [
                   'abigailhaddad@abigailhaddad.com', 'abigail.e.haddad.ctr@mail.mil'
                ],
            },
            Message={
                'Subject': {
                    'Data': "Link to FBO Data Set",
                    'Charset': 'utf-8'
                },
            'Body': {
                'Text': {
                    'Data': f'The FBO Scraper Program has run. The most recent data is at {FileName}.',
                    'Charset': 'utf-8'
                }
            }
        }
    )
    print(response)

def pull_it_together(days):
    print("We started")
    df=grab_date_range(days)
    print("Got the API.")
    df=filter_by_real(df, 'zip')
    df=filter_by_agency(df)
    print("Filtered.")
    df['desc']=df['desc'].apply(cleanhtml)
    print("Cleaned html.")
    df=clean_column_names(df)
    print("Cleaned column names.")
    df=gen_var_with_in_string(df, "Description", "train", "Train in Desc")
    df=gen_var_with_in_string(df, 'Solicitation Name', "train", "Train in SolName")
    print("Generated strings in fields.")
    df=read_merge_naics_descriptions(df)
    print("merged stuff in.")
    df=read_merge_procurement_codes(df)
    print(f"I did everything but the hard part. My DataFrame is {len(df)} lines long.")
    df=get_fields_from_scraping(df)
    print("about to output.")
    FileName=clean_up_and_output(df)
    Message=upload(FileName)
    send_email(Message)
    return(df)

def upload(FileName):
    Bucket, Key = "fbo-scraper", 'fbo-data/' + FileName
    s3 = boto3.resource('s3')
    resp = s3.meta.client.upload_file(sys.argv[3] + FileName, Bucket, Key)
    object = s3.Bucket("fbo-scraper").Object( 'fbo-data/' + FileName)
    object.Acl().put(ACL='public-read')
    print(resp)
    url = '{}/{}/{}'.format(s3_client.meta.endpoint_url, Bucket, Key)
    print(url)
    return(url)

if __name__ == "__main__":
    df=pull_it_together(7)