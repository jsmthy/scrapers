import scrapy

from tpdb.BaseSceneScraper import BaseSceneScraper
import re
import dateparser
import json
import html
import string
from urllib.parse import urlparse
import time

from datetime import datetime
from tpdb.items import SceneItem

# AdultCentro won't allow concurrent requests to multiple sites from what I cane tell
# So you'll have to call this one at a time with a '-a site=xxxxxxx' flag
# Site should equal one of the available keys


class networkAdultCentroSpider(BaseSceneScraper):
    name = 'AdultCentro'
    site = ''

    sites = {
        'mylifeinmiami': 'https://www.mylifeinmiami.com',
        'cospimps': 'https://cospimps.com',
        'jerkoffwithme': 'https://jerkoffwithme.com',
    }

    selector_map = {
        'title': '',
        'description': '',
        'date': '',
        'image': '',
        'performers': '',
        'tags': '',
        'trailer': '',
        'external_id': r'scene/(\d+)/',
        'pagination': '/home_page=%s'
    }

    def start_requests(self):
        link = ''
        if self.site:
            if self.site in self.sites:
                link = self.sites[self.site]
        
        if not link:
            print(f'Scraper requires a site with -a site=xxxxx flag.')
            print(f'Current available options are {self.sites}')
            self.crawler.engine.close_spider(self, reason='No Site Selected')
        else:
            yield scrapy.Request(link + '/videos/', callback=self.start_requests_2, meta={'link':link})

    def start_requests_2(self, response):
        
        appscript = response.xpath('//script[contains(text(),"fox.createApplication")]/text()').get()
        meta = response.meta
        if meta['link']:
            if appscript:
                ah = re.search(r'"ah":"(.*?)"', appscript).group(1)
                aet = re.search(r'"aet":([0-9]+?),', appscript).group(1)
                if ah and aet:
                    print(f'ah: {ah}')
                    print(f'aet: {aet}')
                    token = ah[::-1] + "/" + str(aet)
                    print(f'Token: {token}')

            if not token:
                quit()
            else:
                meta['token'] = token

            
            url = self.get_next_page_url(meta['link'], self.page, meta['token'])
            meta['page'] = self.page
            yield scrapy.Request(url, callback=self.parse, meta=meta)

    def parse(self, response, **kwargs):
        scenes = self.get_scenes(response)
        count = 0
        for scene in scenes:
            count += 1
            yield scene

        if count:
            if 'page' in response.meta and response.meta['page'] < self.limit_pages:
                meta = response.meta
                meta['page'] = meta['page'] + 1
                print('NEXT PAGE: ' + str(meta['page']))
                yield scrapy.Request(url=self.get_next_page_url(response.url, meta['page'], meta['token']),
                                     callback=self.parse,
                                     meta=meta)

    def get_next_page_url(self, base, page, token):
        if "sapi" in base:
            uri = urlparse(base)
            base = uri.scheme + "://" + uri.netloc
        page = str((int(page) - 1) * 10)
        if "miami" in base:
            page_url = base + '/sapi/' + token + '/event.last?_method=event.last&offset={}&limit=10&metaFields[totalCount]=1&transitParameters[v1]=ykYa8ALmUD&transitParameters[v2]=ykYa8ALmUD&transitParameters[showOnHome]=true'
        if "cospimps" in base:
            page_url = base + '/sapi/' + token + '/content.load?_method=content.load&tz=-4&class=Adultcentro%5CAmc%5CObject%5CContent&limit=10&offset={}&transitParameters[v1]=OhUOlmasXD&transitParameters[v2]=OhUOlmasXD&transitParameters[preset]=videos'
        if "jerkoff" in base:
            page_url = base + '/sapi/' + token + '/content.load?_method=content.load&tz=-4&limit=10&offset={}&transitParameters[v1]=OhUOlmasXD&transitParameters[v2]=OhUOlmasXD&transitParameters[preset]=videos'
        return self.format_url(base, page_url.format(page))

    def get_scenes(self, response):
        meta = response.meta
        global json
        jsondata = json.loads(response.text)
        jsondata = jsondata['response']['collection']

        # ~ json_formatted_str = json.dumps(jsondata, indent=2)
        # ~ print(json_formatted_str)      
        # ~ print(response.text)  

        for scene in jsondata:
            # ~ json_formatted_str = json.dumps(scene, indent=2)
            # ~ print(json_formatted_str)  
            if "miami" in response.url:
                scene_id = scene['_typedParams']['id']
            if "cospimps" in response.url or "jerkoff" in response.url:
                scene_id = scene['id']
            scene_url = self.format_url(response.url, '/sapi/' + meta['token'] + '/content.load?_method=content.load&tz=-4&filter[id][fields][0]=id&filter[id][values][0]=%s&limit=1&transitParameters[v1]=ykYa8ALmUD&transitParameters[preset]=scene' % scene_id)
            yield scrapy.Request(scene_url, callback=self.parse_scene, headers=self.headers, cookies=self.cookies, meta=meta)

    def parse_scene(self, response):
        meta=response.meta
        item = SceneItem()
        global json

        jsondata = response.text
        jsondata = jsondata.replace('\r\n', '')
        try:
            data = json.loads(jsondata.strip())
        except:
            print(f'JSON Data: {jsondata}')

        # ~ json_formatted_str = json.dumps(data, indent=2)
        # ~ print(json_formatted_str)        

        data = data['response']['collection'][0]

        item['id'] = data['id']
        item['title'] = string.capwords(html.unescape(data['title']))
        item['description'] = html.unescape(data['description'].strip())
        item['date'] = dateparser.parse(data['sites']['collection'][str(item['id'])]['publishDate'].strip()).isoformat()

        item['performers'] = []
        item['tags'] = []
        if "jerkoff" in response.url:
            performers = data['tags']['collection']
            for performer in performers:
                performername = performers[performer]['alias'].strip().title()
                if performername:
                    item['performers'].append(performername)
        else:
            tags = data['tags']['collection']
            for tag in tags:
                tagname = tags[tag]['alias'].strip().title()
                if tagname:
                    item['tags'].append(tagname)

        item['url'] = self.format_url(response.url, 'scene/' + str(item['id']))
        item['image'] = data['_resources']['primary'][0]['url']
        if "miami" in response.url:
            item['trailer'] = data['_resources']['hoverPreview']
        if "cospimps" in response.url:
            item['trailer'] = "https://cospimps.com/api/download/{}/hd1080/stream?video=1".format(item['id'])
        if "jerkoff" in response.url:
            item['trailer'] = ''
            
        if "jerkoff" in response.url:
            item['site'] = 'Jerk Off With Me'
            item['parent'] = 'Jerk Off With Me'
            item['network'] = 'Jerk Off With Me'
            yield item
            
        if "miami" in response.url:
            item['site'] = 'My Life In Miami'
            item['parent'] = 'My Life In Miami'
            item['network'] = 'My Life In Miami'
            item['performers'] = []
            yield item
            
        if "cospimps" in response.url:
            item['site'] = 'Cospimps'
            item['parent'] = 'Cospimps'
            item['network'] = 'Cospimps'
            modelurl = "https://cospimps.com/sapi/{}/model.getModelContent?_method=model.getModelContent&tz=-4&transitParameters[contentId]={}".format(meta['token'], item['id'])
            meta['item'] = item
            yield scrapy.Request(modelurl, callback=self.get_performers_json, meta=meta)


    def get_performers_json(self, response):
        meta = response.meta
        item = meta['item']

        jsontext = response.text
        performers = re.findall('stageName\":\"(.*?)\"', jsontext)
        if performers:
            item['performers'] = performers
        else:
            item['performers'] = []
        
        yield item