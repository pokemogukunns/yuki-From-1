import json
import requests
import urllib.parse
import time
import datetime
import random
import os
import subprocess
from cache import cache  # キャッシュ管理用
from fastapi import FastAPI, Depends, HTTPException
from fastapi import Response, Cookie, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse as redirect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Union

# 定数
max_api_wait_time = 3  # APIリクエストの最大待機時間（秒）
max_time = 10  # プロセスの最大実行時間（秒）
apis = [r"https://youtube.privacyplz.org/", r"https://inv.nadeko.net/"]  # APIエンドポイントリスト

app = FastAPI()

# テンプレート設定
templates = Jinja2Templates(directory="templates")

# クッキーのチェック関数
def check_cookie(cookie_value: str) -> bool:
    return cookie_value == "True"

# 動画データを非同期に取得する関数
async def get_data(videoid: str):
    # 仮のAPIリクエスト
    try:
        # APIリクエストのURL構築
        url = f"https://youtube.privacyplz.org/api/v1/videos/{urllib.parse.quote(videoid)}"
        response = requests.get(url)  # requestsを非同期でなく使用するため、httpxなどを使うとよい

        # レスポンスが正常でない場合の処理
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to retrieve video data")

        t = response.json()  # JSONデータを取得

        return [
            [{"id": i["videoId"], "title": i["title"], "authorId": i["authorId"], "author": i["author"]} for i in t["recommendedVideos"]],
            list(reversed([i["url"] for i in t["formatStreams"]]))[:2],
            t["descriptionHtml"].replace("\n", "<br>"),
            t["title"],
            t["authorId"],
            t["author"],
            t["authorThumbnails"][-1]["url"]
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching video data: {str(e)}")

# 検索結果を非同期に取得する関数
async def get_search(q: str, page: Union[int, None] = 1):
    try:
        url = f"https://youtube.privacyplz.org/api/v1/search?q={urllib.parse.quote(q)}&page={page}&hl=jp"
        response = requests.get(url)

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to retrieve search data")

        t = response.json()

        def load_search(i):
            if i["type"] == "video":
                return {"title": i["title"], "id": i["videoId"], "authorId": i["authorId"], "author": i["author"], 
                        "length": str(datetime.timedelta(seconds=i["lengthSeconds"])), "published": i["publishedText"], "type": "video"}
            elif i["type"] == "playlist":
                return {"title": i["title"], "id": i["playlistId"], "thumbnail": i["videos"][0]["videoId"], "count": i["videoCount"], "type": "playlist"}
            else:
                if i["authorThumbnails"][-1]["url"].startswith("https"):
                    return {"author": i["author"], "id": i["authorId"], "thumbnail": i["authorThumbnails"][-1]["url"], "type": "channel"}
                else:
                    return {"author": i["author"], "id": i["authorId"], "thumbnail": r"https://" + i["authorThumbnails"][-1]["url"], "type": "channel"}

        return [load_search(i) for i in t["results"]]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching search data: {str(e)}")

# チャンネル情報を非同期で取得する関数（仮実装）
async def get_channel(channelid: str):
    try:
        url = f"https://youtube.privacyplz.org/api/v1/channels/{urllib.parse.quote(channelid)}"
        response = requests.get(url)

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to retrieve channel data")

        t = response.json()

        # チャンネルのデータを取得
        return {
            "channelname": t["author"],
            "channelicon": t["authorThumbnails"][-1]["url"],
            "channelprofile": t["descriptionHtml"],
            "latestVideos": [{"title": i["title"], "videoId": i["videoId"], "author": t["author"], "publishedText": i["publishedText"]} for i in t["latestVideos"]]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching channel data: {str(e)}")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    if not check_cookie(yuki):
        return redirect("/")
          response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)
    
    # ホームページに必要なデータをここで準備
    return templates.TemplateResponse("home.html", {
        "request": request,
        "proxy": proxy
    })


@app.get("/pass", response_class=HTMLResponse)
async def pass_page(request: Request, proxy: Union[str] = Cookie(None)):
    # クッキー設定なし
    return templates.TemplateResponse("pass.html", {
        "request": request,
        "proxy": proxy
    })
    
# 動画ページ
@app.get('/watch', response_class=HTMLResponse)
async def video(v: str, response: Response, request: Request, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    if not check_cookie(yuki):
        return redirect("/")
    
    response.set_cookie(key="yuki", value="True", max_age=7 * 24 * 60 * 60)

    videoid = v
    try:
        t = await get_data(videoid)
    except HTTPException as e:
        return templates.TemplateResponse("error.html", {"request": request, "message": e.detail})

    return templates.TemplateResponse('video.html', {
        "request": request,
        "videoid": videoid,
        "videourls": t[1],
        "res": t[0],
        "description": t[2],
        "videotitle": t[3],
        "authorid": t[4],
        "authoricon": t[6],
        "author": t[5],
        "proxy": proxy
    })

# 検索ページ
@app.get("/search", response_class=HTMLResponse)
async def search(q: str, response: Response, request: Request, page: Union[int, None] = 1, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    if not check_cookie(yuki):
        return redirect("/")
    
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)

    try:
        results = await get_search(q, page)
    except HTTPException as e:
        return templates.TemplateResponse("error.html", {"request": request, "message": e.detail})

    return templates.TemplateResponse("search.html", {
        "request": request,
        "results": results,
        "word": q,
        "next": f"/search?q={q}&page={page + 1}",
        "proxy": proxy
    })

# チャンネルページ
@app.get("/channel/{channelid}", response_class=HTMLResponse)
async def channel(channelid: str, response: Response, request: Request, yuki: Union[str] = Cookie(None), proxy: Union[str] = Cookie(None)):
    if not check_cookie(yuki):
        return redirect("/")
    
    response.set_cookie("yuki", "True", max_age=60 * 60 * 24 * 7)

    try:
        channel_data = await get_channel(channelid)
    except HTTPException as e:
        return templates.TemplateResponse("error.html", {"request": request, "message": e.detail})

    return templates.TemplateResponse('channel.html', {
        "request": request,
        "channelname": channel_data["channelname"],
        "channelicon": channel_data["channelicon"],
        "channelprofile": channel_data["channelprofile"],
        "latest_videos": channel_data["latestVideos"],
        "proxy": proxy
    })
