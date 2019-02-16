#-*- coding=utf-8 -*-
import eventlet
eventlet.monkey_patch()
from flask import Flask,render_template,redirect,abort,make_response,jsonify,request,url_for,Response
from flask_sqlalchemy import Pagination
from werkzeug.contrib.fixers import ProxyFix
import json
from collections import OrderedDict
import subprocess
import hashlib
import random
import markdown
from function import *
from config import *
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from shelljob import proc
import time
import os
import sys
import re


reload(sys)
sys.setdefaultencoding("utf-8")


#######flask
app=Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app)
app.secret_key=os.path.join(config_dir,'PyOne'+GetConfig('password'))
cache = Cache(app, config={'CACHE_TYPE': 'redis'})
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["200/minute", "50/second"],
)


################################################################################
###################################功能函数#####################################
################################################################################
def md5(string):
    a=hashlib.md5()
    a.update(string.encode(encoding='utf-8'))
    return a.hexdigest()

def GetTotal(path='A:/'):
    key='total:{}'.format(path)
    if rd.exists(key):
        return int(rd.get(key))
    else:
        user,n_path=path.split(':')
        if n_path=='/':
            total=items.find({'grandid':0}).count()
        else:
            f=items.find_one({'path':path})
            pid=f['id']
            total=items.find({'parent':pid}).count()
        rd.set(key,total,300)
        return total


# @cache.memoize(timeout=60*5)
def FetchData(path='A:/',page=1,per_page=50,sortby='lastModtime',order='desc',dismiss=False,search_mode=False):
    if search_mode:
        show_secret=GetConfig('show_secret')
        query=items.find({'name':re.compile(path)})
        resp=[]
        data=query.limit(per_page).collation({"locale": "zh", 'numericOrdering':True})\
                .sort([('order',ASCENDING)])\
                .skip((page-1)*per_page)
        for d in data:
            if show_secret=='no':
                if d['type']=='folder':
                    folder_name=d['path']
                else:
                    folder_name=d['path'].replace(d['name']+'/','')
                _,has_password,_=has_item(folder_name,'.password')
                if has_password!=False:
                    continue
            item={}
            item['name']=d['name']
            item['id']=d['id']
            item['lastModtime']=d['lastModtime']
            item['size']=d['size']
            item['type']=d['type']
            item['path']=d['path']
            if dismiss:
                if d['name'] not in ('README.md','README.txt','readme.md','readme.txt','.password','HEAD.md','HEAD.txt','head.md','head.txt'):
                    resp.append(item)
            else:
                resp.append(item)
        total=len(resp)
        return resp,total
    path=urllib.unquote(path)
    resp=[]
    if sortby not in ['lastModtime','type','size','name']:
        sortby='lastModtime'
    if sortby=='size':
        sortby='size_order'
    if order=='desc':
        order=DESCENDING
    else:
        order=ASCENDING
    try:
        user,n_path=path.split(':')
        if n_path=='/':
            data=items.find({'grandid':0,'user':user}).collation({"locale": "zh", 'numericOrdering':True})\
                .sort([('order',ASCENDING),(sortby,order)])\
                .limit(per_page).skip((page-1)*per_page)
            for d in data:
                item={}
                item['name']=d['name']
                item['id']=d['id']
                item['lastModtime']=d['lastModtime']
                item['size']=d['size']
                item['type']=d['type']
                item['path']=d['path']
                if dismiss:
                    if d['name'] not in ('README.md','README.txt','readme.md','readme.txt','.password','HEAD.md','HEAD.txt','head.md','head.txt'):
                        resp.append(item)
                else:
                    resp.append(item)
            total=GetTotal(path)
        else:
            f=items.find_one({'path':path})
            pid=f['id']
            if f['type']!='folder':
                return f,'files'
            data=items.find({'parent':pid}).collation({"locale": "zh", 'numericOrdering':True})\
                .sort([('order',ASCENDING),(sortby,order)])\
                .limit(per_page).skip((page-1)*per_page)
            for d in data:
                item={}
                item['name']=d['name']
                item['id']=d['id']
                item['lastModtime']=d['lastModtime']
                item['size']=d['size']
                item['type']=d['type']
                item['path']=d['path']
                if dismiss:
                    if d['name'] not in ('README.md','README.txt','readme.md','readme.txt','.password','HEAD.md','HEAD.txt','head.md','head.txt'):
                        resp.append(item)
                else:
                    resp.append(item)
            total=GetTotal(path)
    except:
        resp=[]
        total=0
    return resp,total

@cache.memoize(timeout=60*5)
def _thunbnail(id,user):
    app_url=GetAppUrl()
    token=GetToken(user=user)
    headers={'Authorization':'bearer {}'.format(token),'Content-type':'application/json'}
    url=app_url+'v1.0/me/drive/items/{}/thumbnails/0?select=large'.format(id)
    r=requests.get(url,headers=headers)
    data=json.loads(r.content)
    if data.get('large').get('url'):
        # return data.get('large').get('url').replace('thumbnail','videotranscode').replace('&width=800&height=800','')+'&format=dash&track=audio&transcodeAhead=0&part=initsegment&quality=audhigh'
        return data.get('large').get('url')
        # return data.get('large').get('url').replace('thumbnail','videotranscode').replace('&width=800&height=800','')+'&format=dash&track=audio&transcodeAhead=0&part=initsegment&quality=audhigh'
    else:
        return False

@cache.memoize(timeout=60*5)
def _getdownloadurl(id,user):
    app_url=GetAppUrl()
    token=GetToken(user=user)
    filename=GetName(id)
    ext=filename.split('.')[-1].lower()
    headers={'Authorization':'bearer {}'.format(token),'Content-type':'application/json'}
    url=app_url+'v1.0/me/drive/items/'+id
    r=requests.get(url,headers=headers)
    data=json.loads(r.content)
    if data.get('@microsoft.graph.downloadUrl'):
        downloadUrl=data.get('@microsoft.graph.downloadUrl')
    else:
        downloadUrl=False
    if ext in ['webm','avi','mpg', 'mpeg', 'rm', 'rmvb', 'mov', 'wmv', 'mkv', 'asf']:
        play_url=_thunbnail(id,user)
        play_url=play_url.replace('thumbnail','videomanifest').replace('&width=800&height=800','')+'&part=index&format=dash&useScf=True&pretranscode=0&transcodeahead=0'
        # play_url=re.sub('inputFormat=.*?&','inputFormat=mp4&',play_url)
        # downloadUrl=downloadUrl.replace('thumbnail','videomanifest').replace('&width=800&height=800','')+'&part=index&format=dash&useScf=True&pretranscode=0&transcodeahead=0'
    else:
        play_url=downloadUrl
    return downloadUrl,play_url

def GetDownloadUrl(id,user):
    key_='downloadUrl:{}'.format(id)
    if rd.exists(key_):
        downloadUrl,play_url,ftime=rd.get(key_).split('####')
        if time.time()-int(ftime)>=600:
            # print('{} downloadUrl expired!'.format(id))
            downloadUrl,play_url=_getdownloadurl(id,user)
            ftime=int(time.time())
            k='####'.join([downloadUrl,play_url,str(ftime)])
            rd.set(key_,k)
        else:
            # print('get {}\'s downloadUrl from cache'.format(id))
            downloadUrl=downloadUrl
            play_url=play_url
    else:
        # print('first time get downloadUrl from {}'.format(id))
        downloadUrl,play_url=_getdownloadurl(id,user)
        ftime=int(time.time())
        k='####'.join([downloadUrl,play_url,str(ftime)])
        rd.set(key_,k)
    return downloadUrl,play_url



# @cache.memoize(timeout=60*5)
def GetReadMe(path):
    # README
    ext='Markdown'
    readme,_,i=has_item(path,'README.md')
    if readme==False:
        readme,_,i=has_item(path,'readme.md')
    if readme==False:
        ext='Text'
        readme,_,i=has_item(path,'readme.txt')
    if readme==False:
        ext='Text'
        readme,_,i=has_item(path,'README.txt')
    if readme!=False:
        readme=markdown.markdown(readme, extensions=['tables'])
    return readme,ext


# @cache.memoize(timeout=60*5)
def GetHead(path):
    # README
    ext='Markdown'
    head,_,i=has_item(path,'HEAD.md')
    if head==False:
        head,_,i=has_item(path,'head.md')
    if head==False:
        ext='Text'
        head,_,i=has_item(path,'head.txt')
    if head==False:
        ext='Text'
        head,_,i=has_item(path,'HEAD.txt')
    if head!=False:
        head=markdown.markdown(head, extensions=['tables'])
    return head,ext


def CanEdit(filename):
    ext=filename.split('.')[-1].lower()
    if ext in ["html","htm","php","css","go","java","js","json","txt","sh","md",".password"]:
        return True
    else:
        return False

def CodeType(ext):
    code_type={}
    code_type['html'] = 'html';
    code_type['htm'] = 'html';
    code_type['php'] = 'php';
    code_type['css'] = 'css';
    code_type['go'] = 'golang';
    code_type['java'] = 'java';
    code_type['js'] = 'javascript';
    code_type['json'] = 'json';
    code_type['txt'] = 'Text';
    code_type['sh'] = 'sh';
    code_type['md'] = 'Markdown';
    return code_type.get(ext.lower())

def file_ico(item):
    ext = item['name'].split('.')[-1].lower()
    if ext in ['bmp','jpg','jpeg','png','gif']:
        return "image"

    if ext in ['mp4','mkv','webm','avi','mpg', 'mpeg', 'rm', 'rmvb', 'mov', 'wmv', 'mkv', 'asf']:
        return "ondemand_video"

    if ext in ['ogg','mp3','wav']:
        return "audiotrack"

    return "insert_drive_file"

def _remote_content(fileid,user):
    kc='{}:content'.format(fileid)
    if rd.exists(kc):
        return rd.get(kc)
    else:
        downloadUrl,play_url=GetDownloadUrl(fileid,user)
        if downloadUrl:
            r=requests.get(downloadUrl)
            r.encoding='utf-8'
            content=r.content
            rd.set(kc,content)
            return content
        else:
            return False

# @cache.memoize(timeout=60)
def has_item(path,name):
    if items.count()==0:
        return False,False,False
    key='has_item$#$#$#$#{}$#$#$#$#{}'.format(path,name)
    print('get key:{}'.format(key))
    if rd.exists(key):
        values=rd.get(key)
        item,fid,cur=values.split('########')
        if item=='False':
            item=False
        if cur=='False':
            cur=False
        else:
            cur=True
        if fid=='False':
            fid=False
        return item,fid,cur
    else:
        item=False
        fid=False
        dz=False
        cur=False
        if name=='.password':
            dz=True
        try:
            user,n_path=path.split(':')
            if n_path=='/':
                if items.find_one({'grandid':0,'name':name,'user':user}):
                    fid=items.find_one({'grandid':0,'name':name,'user':user})['id']
                    item=_remote_content(fid,user).strip()
            else:
                route=n_path[1:].split('/')
                if name=='.password':
                    for idx,r in enumerate(route):
                        p=user+':/'+'/'.join(route[:idx+1])
                        f=items.find_one({'path':p})
                        pid=f['id']
                        data=items.find_one({'name':name,'parent':pid})
                        if data:
                            fid=data['id']
                            item=_remote_content(fid,user).strip()
                            if idx==len(route)-1:
                                cur=True
                else:
                    f=items.find_one({'path':path})
                    pid=f['id']
                    data=items.find_one({'name':name,'parent':pid})
                    if data:
                        fid=data['id']
                        item=_remote_content(fid,user).strip()
        except:
            item=False
        rd.set(key,'{}########{}########{}'.format(item,fid,cur))
        return item,fid,cur



def verify_pass_before(path):
    plist=path_list(path)
    for i in [i for i in range(len(plist))]:
        n='/'.join(plist[:-i])
        yield n

def has_verify(path):
    verify=False
    md5_p=md5(path)
    passwd,fid,cur=has_item(path,'.password')
    if fid and cur:
        vp=request.cookies.get(md5_p)
        if passwd==vp:
            verify=True
    else:
        for last in verify_pass_before(path):
            if last=='':
                last='/'
            passwd,fid,cur=has_item(last,'.password')
            md5_p=md5(last)
            vp=request.cookies.get(md5_p)
            if passwd==vp:
                verify=True
    return verify


def path_list(path):
    try:
        path=urllib.unquote(path)
        if path.split(':',1)=='':
            plist=[path+'/']
        else:
            user,n_path=path.split(':',1)
            if n_path.startswith('/'):
                n_path=n_path[1:]
            if n_path.endswith('/'):
                n_path=n_path[:-1]
            plist=n_path.split('/')
            plist=['{}:/{}'.format(user,plist[0])]+plist[1:]
        return plist
    except:
        return []

def get_od_user():
    config_path=os.path.join(config_dir,'config.py')
    with open(config_path,'r') as f:
        text=f.read()
    key='users'
    if rd.exists(key):
        users=json.loads(rd.get(key))
    else:
        value=re.findall('od_users=([\w\W]*})',text)[0]
        users=json.loads(value)
        rd.set(key,value)
    ret=[]
    for user,value in users.items():
        if value.get('client_id')!='':
            #userid,username,endpoint,sharepath,order,
            ret.append(
                    (
                        user,
                        value.get('other_name'),
                        '/{}:'.format(user),
                        value.get('share_path'),
                        value.get('order')
                    )
                )
        else:
            ret.append(
                    (
                        user,
                        '添加网盘',
                        url_for('admin.install',step=0,user=user),
                        value.get('share_path'),
                        value.get('order')
                    )
                )
    ret=sorted(ret,key=lambda x:x[-1],reverse=False)
    return ret

def GetCookie(key,default):
    value=request.args.get(key)
    if value is None:
        value=request.cookies.get(key)
        if value==None or value=='None':
            value=default
    if key=='image_mode':
        value=int(value)
    return value

################################################################################
###################################试图函数#####################################
################################################################################
@app.before_request
def before_request():
    bad_ua=['Googlebot-Image','FeedDemon ','BOT/0.1 (BOT for JCE)','CrawlDaddy ','Java','Feedly','UniversalFeedParser','ApacheBench','Swiftbot','ZmEu','Indy Library','oBot','jaunty','YandexBot','AhrefsBot','MJ12bot','WinHttp','EasouSpider','HttpClient','Microsoft URL Control','YYSpider','jaunty','Python-urllib','lightDeckReports Bot','PHP','vxiaotou-spider','spider']
    global referrer
    try:
        ip = request.headers['X-Forwarded-For'].split(',')[0]
    except:
        ip = request.remote_addr
    try:
        ua = request.headers.get('User-Agent')
    except:
        ua="null"
    if sum([i.lower() in ua.lower() for i in bad_ua])>0:
        return redirect('http://www.baidu.com')
    # print '{}:{}:{}'.format(request.endpoint,ip,ua)
    referrer=request.referrer if request.referrer is not None else 'no-referrer'

@app.errorhandler(500)
def page_not_found(e):
    # note that we set the 500 status explicitly
    return render_template('theme/{}/500.html'.format(GetConfig('theme')),cur_user=''), 500

@app.route('/<path:path>',methods=['POST','GET'])
@app.route('/',methods=['POST','GET'])
@limiter.limit("200/minute;50/second")
def index(path='A:/'):
    path=urllib.unquote(path).replace('&action=play','')
    if path=='favicon.ico':
        return redirect('https://onedrive.live.com/favicon.ico')
    if items.count()==0:
        if not os.path.exists(os.path.join(config_dir,'data/.install')):
            return redirect(url_for('admin.install',step=0,user='A'))
        else:
            #subprocess.Popen('python {} UpdateFile'.format(os.path.join(config_dir,'function.py')),shell=True)
            return make_response('<h1>正在更新数据！如果您是网站管理员，请在后台运行命令：python function.py UpdateFile</h1>')
    try:
        path.split(':')
    except:
        path='A:/'+path
    #参数
    user,n_path=path.split(':')
    if n_path=='':
        path=':'.join([user,'/'])
    page=request.args.get('page',1,type=int)
    image_mode=GetCookie(key='image_mode',default=0)
    sortby=GetCookie(key='sortby',default='lastModtime')
    order=GetCookie(key='order',default='desc')
    action=request.args.get('action','download')
    # try:
    #     action=re.findall('action=(.*)',request.url)[0]
    # except:
    #     action='download'
    data,total = FetchData(path=path,page=page,per_page=50,sortby=sortby,order=order,dismiss=True)
    #是否有密码
    password,_,cur=has_item(path,'.password')
    md5_p=md5(path)
    has_verify_=has_verify(path)
    if request.method=="POST":
        password1=request.form.get('password')
        if password1==password:
            resp=make_response(redirect(url_for('.index',path=path)))
            resp.delete_cookie(md5_p)
            resp.set_cookie(md5_p,password)
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp
    if password!=False:
        if (not request.cookies.get(md5_p) or request.cookies.get(md5_p)!=password) and has_verify_==False:
            if total=='files' and GetConfig('encrypt_file')=="no":
                return show(data['id'],user,action)
            resp=make_response(render_template('theme/{}/password.html'.format(GetConfig('theme')),path=path,cur_user=user))
            resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
            return resp
    if total=='files':
        return show(data['id'],user,action)
    readme,ext_r=GetReadMe(path)
    head,ext_d=GetHead(path)
    #参数
    all_image=False if sum([file_ico(i)!='image' for i in data])>0 else True
    pagination=Pagination(query=None,page=page, per_page=50, total=total, items=None)
    if path.split(':',1)[-1]=='/':
        path=':'.join([path.split(':',1)[0],''])
    resp=make_response(render_template('theme/{}/index.html'.format(GetConfig('theme'))
                    ,pagination=pagination
                    ,items=data
                    ,path=path
                    ,image_mode=image_mode
                    ,readme=readme
                    ,ext_r=ext_r
                    ,head=head
                    ,ext_d=ext_d
                    ,sortby=sortby
                    ,order=order
                    ,cur_user=user
                    ,all_image=all_image
                    ,endpoint='.index'))
    resp.set_cookie('image_mode',str(image_mode))
    resp.set_cookie('sortby',str(sortby))
    resp.set_cookie('order',str(order))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/file/<user>/<fileid>/<action>')
def show(fileid,user,action='download'):
    name=GetName(fileid)
    ext=name.split('.')[-1].lower()
    path=GetPath(fileid)
    url=request.url.replace(':80','').replace(':443','').encode('utf-8').split('?')[0]
    inner_url='/'+urllib.quote('/'.join(url.split('/')[3:]))
    if request.method=='POST' or action=='share':
        print(u'share page:{}'.format(path))
        if ext in ['csv','doc','docx','odp','ods','odt','pot','potm','potx','pps','ppsx','ppsxm','ppt','pptm','pptx','rtf','xls','xlsx']:
            downloadUrl,play_url=GetDownloadUrl(fileid,user)
            url = 'https://view.officeapps.live.com/op/view.aspx?src='+urllib.quote(downloadUrl)
            resp=make_response(redirect(url))
        elif ext in ['bmp','jpg','jpeg','png','gif']:
            resp=make_response(render_template('theme/{}/show/image.html'.format(GetConfig('theme')),url=url,inner_url=inner_url,path=path,cur_user=user))
        elif ext in ['mp4','webm']:
            resp=make_response(render_template('theme/{}/show/video.html'.format(GetConfig('theme')),url=url,inner_url=inner_url,path=path,cur_user=user))
        elif ext in ['avi','mpg', 'mpeg', 'rm', 'rmvb', 'mov', 'wmv', 'mkv', 'asf']:
            resp=make_response(render_template('theme/{}/show/video2.html'.format(GetConfig('theme')),url=url,inner_url=inner_url,path=path,cur_user=user))
        elif ext in ['ogg','mp3','wav']:
            resp=make_response(render_template('theme/{}/show/audio.html'.format(GetConfig('theme')),url=url,inner_url=inner_url,path=path,cur_user=user))
        elif CodeType(ext) is not None:
            content=_remote_content(fileid,user)
            resp=make_response(render_template('theme/{}/show/code.html'.format(GetConfig('theme')),content=content,url=url,inner_url=inner_url,language=CodeType(ext),path=path,cur_user=user))
        elif name=='.password':
            resp=make_response(abort(404))
        else:
            downloadUrl,play_url=GetDownloadUrl(fileid,user)
            resp=make_response(redirect(downloadUrl))
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        return resp
    print('action:{}'.format(action))
    if name=='.password':
        resp=make_response(abort(404))
    if 'no-referrer' in GetConfig('allow_site').split(',') or sum([i in referrer for i in GetConfig('allow_site').split(',')])>0:
        downloadUrl,play_url=GetDownloadUrl(fileid,user)
        if ext in ['webm','avi','mpg', 'mpeg', 'rm', 'rmvb', 'mov', 'wmv', 'mkv', 'asf']:
            if action=='play':
                resp=make_response(redirect(play_url))
            else:
                resp=make_response(redirect(downloadUrl))
        else:
            resp=make_response(redirect(play_url))
    else:
        resp=make_response(abort(404))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp



@app.route('/py_find/<key_word>')
def find(key_word):
    page=request.args.get('page',1,type=int)
    ajax=request.args.get('ajax','no')
    image_mode=request.args.get('image_mode')
    sortby=request.args.get('sortby')
    order=request.args.get('order')
    action=request.args.get('action','download')
    data,total=FetchData(path=key_word,page=page,per_page=50,sortby=sortby,order=order,dismiss=True,search_mode=True)
    pagination=Pagination(query=None,page=page, per_page=50, total=total, items=None)
    if ajax=='yes':
        retdata={}
        retdata['code']=0
        retdata['msg']=""
        retdata['total']=total
        retdata['data']=[]
        for d in data:
            info={}
            if d['type']=='folder':
                info['name']='<a href="'+url_for('.index',path=d['path'])+'">'+d['name']+'</a>'
            else:
                info['name']='<a href="'+url_for('.index',path=d['path'],action='share')+'" target="_blank">'+d['name']+'</a>'
            info['type']=d['type']
            info['lastModtime']=d['lastModtime']
            info['size']=d['size']
            info['path']=d['path']
            info['id']=d['id']
            retdata['data'].append(info)
        return jsonify(retdata)
    resp=make_response(render_template('theme/{}/find.html'.format(GetConfig('theme'))
                    ,pagination=pagination
                    ,items=data
                    ,path='/'
                    ,sortby=sortby
                    ,order=order
                    ,key_word=key_word
                    ,cur_user='搜索:"{}"'.format(key_word)
                    ,endpoint='.find'))
    resp.set_cookie('image_mode',str(image_mode))
    resp.set_cookie('sortby',str(sortby))
    resp.set_cookie('order',str(order))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/robots.txt')
def robot():
    resp="""
User-agent:  *
Disallow:  /
    """
    resp=make_response(resp)
    resp.headers['Content-Type'] = 'text/javascript; charset=utf-8'
    return resp


######################注册应用
from admin import admin as admin_blueprint
app.register_blueprint(admin_blueprint)

######################初始化变量
rd.set('title',title)
rd.set('tj_code',tj_code)
rd.set('downloadUrl_timeout',downloadUrl_timeout)
rd.set('allow_site',','.join(allow_site))
rd.set('ARIA2_HOST',ARIA2_HOST)
rd.set('ARIA2_PORT',ARIA2_PORT)
rd.set('ARIA2_SECRET',ARIA2_SECRET)
rd.set('ARIA2_SCHEME',ARIA2_SCHEME)
rd.set('password',password)
config_path=os.path.join(config_dir,'config.py')
with open(config_path,'r') as f:
    text=f.read()
rd.set('users',re.findall('od_users=([\w\W]*})',text)[0])
key='themelist'
rd.delete(key)
######################函数
app.jinja_env.globals['FetchData']=FetchData
app.jinja_env.globals['path_list']=path_list
app.jinja_env.globals['CanEdit']=CanEdit
app.jinja_env.globals['quote']=urllib.quote
app.jinja_env.globals['len']=len
app.jinja_env.globals['enumerate']=enumerate
app.jinja_env.globals['os']=os
app.jinja_env.globals['re']=re
app.jinja_env.globals['file_ico']=file_ico
app.jinja_env.globals['GetConfig']=GetConfig
app.jinja_env.globals['GetThemeList']=GetThemeList
app.jinja_env.globals['get_od_user']=get_od_user
################################################################################
#####################################启动#######################################
################################################################################
if __name__=='__main__':
    app.run(port=58693,debug=True)




