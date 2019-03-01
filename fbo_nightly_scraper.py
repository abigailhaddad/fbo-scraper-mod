#!/usr/bin/env python3
import urllib.request
from contextlib import closing
import shutil
import re
from collections import Counter
import os
from datetime import datetime
import json



class NightlyFBONotices():
    '''
    Download nightly FBO file, converting pseudo-xml into JSON.

    Attributes:
        date (str): The date of the nightly file to download. Format:  YYYYMMDD
                    (e.g. '20180506')
        base_url (str): the base url for the FBO FTP. By default it is set to:
                        ftp://ftp.fbo.gov/FBOFeed
        notice_types (list): list of uppercase strings representing the notice types to fetch. None by default. List values must
                             match FBO notation. For example, pre-solicitation type notices are PRESOL. A full list can be found 
                             under the General Info section online at https://www.fbo.gov/?&static=interface
        naics (list): a list of strings where each represents either a full naics code or the first few characters as a wildcard.
                      These will also be used to filter the notices that are fetched.
    '''

    def __init__(self, date, base_url='ftp://ftp.fbo.gov/FBOFeed', notice_types = None, naics = None):
        self.base_url = base_url
        self.date = str(date)
        self.ftp_url = base_url+self.date
        self.notice_types = notice_types
        self.naics = naics
        

    @staticmethod
    def _id_and_count_notice_tags(file_lines):
        '''
        Static method to count the number of notice tags within an FBO export.

        Attributes:
            file_lines (list): A list of lines from the nightly FBO file.

        Returns:
            tag_count (dict): An instance of a collections.Counter object
                               containing tags as keys and their counts as
                               values
        '''

        end_tag = re.compile(r'\</[A-Z]*>')
        alphas_re = re.compile('[^a-zA-Z]')
        tags = []   # instantiate empty list
        for line in file_lines:
            try:
                match = end_tag.search(line)
                m = match.group()
                tags.append(m)
            except AttributeError:
                # these are all of the non record-type tags
                pass 
        clean_tags = [alphas_re.sub('', x) for x in tags]
        tag_count = Counter(clean_tags)

        return tag_count


    @staticmethod
    def _merge_dicts(dicts):
        d = {}
        for dict in dicts:
            for key in dict:
                try:
                    d[key].append(dict[key])
                except KeyError:
                    d[key] = [dict[key]]
        return {k:" ".join(v) for k, v in d.items()}


    @staticmethod
    def _make_out_path(out_path):
        if not os.path.exists(out_path):
            os.makedirs(out_path)


    def download_from_ftp(self):
        '''
        Downloads a nightly FBO file, reads the lines, then removes file.
        Compare to read_from_ftp()

        Returns:
            file_lines (list): the lines of the nightly file
        '''

        file_name = 'fbo_nightly_'+self.date
        out_path = os.path.join(os.getcwd(),"temp","nightly_files")
        NightlyFBONotices._make_out_path(out_path)
        try:
            with closing(urllib.request.urlopen(self.ftp_url)) as r:
                file_name = os.path.join(out_path,file_name)
                with open(file_name, 'wb') as f:
                    shutil.copyfileobj(r, f)
        except Exception as err:
            return
        with open(file_name,'r', errors='ignore') as f:
            file_lines = f.readlines()
        os.remove(file_name)
        
        return file_lines


    def pseudo_xml_to_json(self, file_lines):
        '''
        Open nightly file and convert the pseudo-xml to JSON

        Arguments:
            file_name (str): the absolute path to the downloaded file

        Returns:
            json_str (str): a string representing the JSON
        '''

        html_tags = ['a', 'abbr', 'acronym', 'address', 'applet', 'area', 'article', 'aside', 'audio', 'b', 'base', 'basefont', 
                     'bdi', 'bdo', 'bgsound', 'big', 'blink', 'blockquote', 'body', 'br', 'button', 'canvas', 'caption', 'center',
                     'cite', 'code', 'col', 'colgroup', 'command', 'content', 'data', 'datalist', 'dd', 'del', 'details', 'dfn', 
                     'dialog', 'dir', 'div', 'dl', 'dt', 'element', 'em', 'embed', 'fieldset', 'figcaption', 'figure', 'font', 
                     'footer', 'form', 'frame', 'frameset', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hgroup', 'hr', 
                     'html', 'i', 'iframe', 'image', 'img', 'input', 'ins', 'isindex', 'kbd', 'keygen', 'label', 'legend', 'li', 
                     'link', 'listing', 'main', 'map', 'mark', 'marquee', 'math', 'menu', 'menuitem', 'meta', 'meter', 'multicol', 
                     'nav', 'nextid', 'nobr', 'noembed', 'noframes', 'noscript', 'object', 'ol', 'optgroup', 'option', 'output', 
                     'p', 'param', 'picture', 'plaintext', 'pre', 'progress', 'q', 'rb', 'rbc', 'rp', 'rt', 'rtc', 'ruby', 's', 
                     'samp', 'script', 'section', 'select', 'shadow', 'slot', 'small', 'source', 'spacer', 'span', 'strike', 
                     'strong', 'style', 'sub', 'summary', 'sup', 'svg', 'table', 'tbody', 'td', 'template', 'textarea', 'tfoot', 
                     'th', 'thead', 'time', 'title', 'tr', 'track', 'tt', 'u', 'ul', 'var', 'video', 'wbr', 'xmp']
        html_tag_re = re.compile(r'|'.join('(?:</?{0}>)'.format(x) for x in html_tags))
        alphas_re = re.compile('[^a-zA-Z]')
        notice_types = {'PRESOL','SRCSGT','SNOTE','SSALE','COMBINE','AMDCSS',
                        'MOD','AWARD','JA','FAIROPP','ARCHIVE','UNARCHIVE',
                        'ITB','FSTD','EPSUPLOAD','DELETE'}
        notice_type_start_tag_re = re.compile(r'|'.join('(?:<{0}>)'.\
                                              format(x) for x in notice_types))
        notice_type_end_tag_re = re.compile(r'|'.join('(?:</{0}>)'.\
                                            format(x) for x in notice_types))
        # returns two groups: the sub-tag as well as the text corresponding to it
        sub_tag_groups = re.compile(r'\<([a-z]*)\>(.*)')
        notices_dict_incrementer = {k:0 for k in notice_types}
        tag_count = NightlyFBONotices._id_and_count_notice_tags(file_lines)
        matches_dict = {k:{k:[] for k in range(v)} for k,v in tag_count.items()}
        # Loop through each line searching for start-tags, then end-tags, then
        # sub-tags (after stripping html) and then ensuring that every line of
        # multi-line tag values is captured.
        last_clean_notice_start_tag = ''
        last_sub_tab = ''
        for line in file_lines:
            try:
                match = notice_type_start_tag_re.search(line)
                m = match.group()
                clean_notice_start_tag = alphas_re.sub('', m)
                last_clean_notice_start_tag = clean_notice_start_tag
            except AttributeError:
                try:
                    match = notice_type_end_tag_re.search(line)
                    m = match.group()
                    #clean_notice_end_tag = alphas_re.sub('', m).strip()
                    notices_dict_incrementer[last_clean_notice_start_tag] += 1
                    continue #continue since we found an ending notice tag
                except AttributeError:
                    #line_lower = line.lower().replace(u'\xa0', u' ')
                    #I MODIFIED THIS SO IT'S NO LONGER MAKING EVERYTHING LOWERCASE 
                    #WHILE STILL MAKING THE CLASSES LOWERCASE
                    line_lower=line.split(">")[0].lower()+">"+line.split(">")[-1].replace(u'\xa0', u' ')
                    if len(line.split(">"))<2:
                        line_lower=line.replace(u'\xa0', u' ')
                    line_lower_htmless = ' '.join(html_tag_re.sub(' ',line_lower).split())
                    try:
                        matches = sub_tag_groups.search(line_lower_htmless)
                        groups  = matches.groups()
                        sub_tag = groups[0]
                        last_sub_tab = sub_tag
                        sub_tag_text = groups[1]
                        current_tag_index = notices_dict_incrementer[last_clean_notice_start_tag]
                        matches_dict[last_clean_notice_start_tag][current_tag_index].append({sub_tag:sub_tag_text})
                    except AttributeError:
                        record_index = 0
                        for i,record in enumerate(matches_dict[last_clean_notice_start_tag][current_tag_index]):
                            if last_sub_tab in record:
                                record_index = i
                        matches_dict[last_clean_notice_start_tag][current_tag_index][record_index][last_sub_tab] += " " + line_lower_htmless
        notices_dict = {k:None for k in notice_types}
        for k in matches_dict:
            dict_list = [v for k,v in matches_dict[k].items()]
            notices_dict[k] = dict_list

        merge_notices_dict = {k:[] for k in notices_dict}
        for k in notices_dict:
            notices = notices_dict[k]
            if notices:
                for notice in notices:
                    merged_dict = NightlyFBONotices._merge_dicts(notice)
                    merge_notices_dict[k].append(merged_dict)
            else:
                pass
        json_str = json.dumps(merge_notices_dict)

        return json_str