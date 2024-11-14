import json
import requests
import urllib.parse
import datetime
import os
from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.exceptions import HTTPException
from typing import Union
from starlette.responses import RedirectResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.cache import Cache

# FastAPIのインスタンス作成
app = FastAPI()

# APIリスト（プライバシー用API等）
apis = [r"https://youtube.privacyplz.org/", r"https://inv.nadeko.net/"]

# キャッシュ設定（任意）
cache = Cache()

# グローバル変数
apichannels = []
apicomments = []

# 必要な外部リクエストを送る関数
def apirequest(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        response.raise_for_status()

def apichannelrequest(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        response.raise_for_status()

def apicommentsrequest(url):
    response = requests.get(url)
    if response.status_code == 200:
        return response.text
    else:
        response.raise_for_status()

# 動画情報を取得する関数
def get_data(videoid):
    t = json.loads(apirequest(apis[0] + "api/v1/videos/" + urllib.parse.quote(videoid)))
    return [{"id": i["videoId"], "title": i["title"], "authorId": i["authorId"], "author": i["author"]} for i in t["recommendedVideos"]], list(reversed([i["url"] for i in t["formatStreams"]]))[:2], t["descriptionHtml"].replace("\n", "<br>"), t["title"], t["authorId"], t["author"], t["authorThumbnails"][-1]["url"]

# 検索結果を取得する関数
def get_search(q, page):
    t = json.loads(apirequest(apis[0] + f"api/v1/search?q={urllib.parse.quote(q)}&page={page}&hl=jp"))
    
    def load_search(i):
        if i["type"] == "video":
            return {"title": i["title"], "id": i["videoId"], "authorId": i["authorId"], "author": i["author"], 
                    "length": str(datetime.timedelta(seconds=i["lengthSeconds"])), "published": i["publishedText"], "type": "video"}
        elif i["type"] == "playlist":
            return {"title": i["title"], "id": i["playlistId"], "thumbnail": i["videos"][0]["videoId"], "count": i["videoCount"], "type": "playlist"}
        else:
            return {"author": i["author"], "id": i["authorId"], "thumbnail": i["authorThumbnails"][-1]["url"], "type": "channel"}
    
    return [load_search(i) for i in t]

# チャンネル情報を取得する関数
def get_channel(channelid):
    t = json.loads(apichannelrequest(apis[0] + "api/v1/channels/" + urllib.parse.quote(channelid)))
    if not t["latestVideos"]:
        raise HTTPException(status_code=500, detail="APIがチャンネルを返しませんでした")
    
    return [{"title": i["title"], "id": i["videoId"], "authorId": t["authorId"], "author": t["author"], "published": i["publishedText"], "type": "video"} for i in t["latestVideos"]], {"channelname": t["author"], "channelicon": t["authorThumbnails"][-1]["url"], "channelprofile": t["descriptionHtml"]}

# プレイリスト情報を取得する関数
def get_playlist(listid, page):
    t = json.loads(apirequest(apis[0] + f"/api/v1/playlists/{urllib.parse.quote(listid)}?page={urllib.parse.quote(page)}"))
    return [{"title": i["title"], "id": i["videoId"], "authorId": i["authorId"], "author": i["author"], "type": "video"} for i in t["videos"]]

# コメント情報を取得する関数
def get_comments(videoid):
    t = json.loads(apicommentsrequest(apis[0] + f"api/v1/comments/{urllib.parse.quote(videoid)}?hl=jp"))
    return [{"author": i["author"], "authoricon": i["authorThumbnails"][-1]["url"], "authorid": i["authorId"], "body": i["contentHtml"].replace("\n", "<br>")} for i in t["comments"]]

# ホーム画面
@app.get("/")
def home():
    return {"message": "Welcome to the YouTube-like API!"}

# 動画情報表示
@app.get('/watch', response_class=HTMLResponse)
def video(v: str, response: Response, request: Request):
    videoid = v
    t = get_data(videoid)
    
    return template('video.html', {
        "request": request,
        "videoid": videoid,
        "videourls": t[1],
        "res": t[0],
        "description": t[2],
        "videotitle": t[3],
        "authorid": t[4],
        "authoricon": t[6],
        "author": t[5],
        "proxy": None
    })

# 検索結果表示
@app.get("/search", response_class=HTMLResponse)
def search(q: str, response: Response, request: Request, page: Union[int, None] = 1):
    return template("search.html", {
        "request": request,
        "results": get_search(q, page),
        "word": q,
        "next": f"/search?q={q}&page={page + 1}",
        "proxy": None
    })

# ハッシュタグ検索
@app.get("/hashtag/{tag}")
def hashtag(tag: str):
    return RedirectResponse(f"/search?q={tag}")

# チャンネル情報表示
@app.get("/channel/{channelid}", response_class=HTMLResponse)
def channel(channelid: str, response: Response, request: Request):
    t = get_channel(channelid)
    return template("channel.html", {
        "request": request,
        "results": t[0],
        "channelname": t[1]["channelname"],
        "channelicon": t[1]["channelicon"],
        "channelprofile": t[1]["channelprofile"],
        "proxy": None
    })

# プレイリスト表示
@app.get("/playlist", response_class=HTMLResponse)
def playlist(list: str, response: Response, request: Request, page: Union[int, None] = 1):
    return template("search.html", {
        "request": request,
        "results": get_playlist(list, str(page)),
        "word": "",
        "next": f"/playlist?list={list}",
        "proxy": None
    })

# コメント表示
@app.get("/comments")
def comments(request: Request, v: str):
    return template("comments.html", {"request": request, "comments": get_comments(v)})

# サムネイル画像表示
@app.get("/thumbnail")
def thumbnail(v: str):
    return Response(content=requests.get(f"https://img.youtube.com/vi/{v}/0.jpg").content, media_type="image/jpeg")

# API情報表示
@app.get("/info", response_class=HTMLResponse)
def viewlist(response: Response, request: Request):
    global apis, apichannels, apicomments
    return template("info.html", {
        "request": request,
        "Youtube_API": apis[0],
        "Channel_API": apichannels[0],
        "Comments_API": apicomments[0]
    })

# APIの推測レベル表示
@app.get("/answer")
def set_cokie(q: str):
    t = get_level(q)
    if t > 5:
        return f"level{t}\n推測を推奨する"
    elif t == 0:
        return "level12以上\nほぼ推測必須"
    return f"level{t}\n覚えておきたいレベル"

# エラーハンドリング
@app.exception_handler(500)
def api_error(request: Request, exc: Exception):
    return template("APIwait.html", {"request": request}, status_code=500)

@app.exception_handler(APItimeoutError)
def api_timeout_error(request: Request, exception: APItimeoutError):
    return template("APIwait.html", {"request": request}, status_code=500)
