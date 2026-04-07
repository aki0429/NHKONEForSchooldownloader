import requests
import subprocess
import re
import os
import sys

def load_cookies_from_txt(file_path="Cookie.txt"):
    cookie_dict = {}
    raw_cookie_list = []
    if not os.path.exists(file_path):
        print(f"警告: {file_path} が見つかりません。Cookieなしで試行します。")
        return None, None

    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) >= 7:
                name, value = parts[5], parts[6]
                cookie_dict[name] = value
                raw_cookie_list.append(f"{name}={value}")
    
    ffmpeg_cookie = "; ".join(raw_cookie_list)
    return cookie_dict, ffmpeg_cookie

def time_to_seconds(time_str):
    try:
        h, m, s = time_str.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except:
        return 0.0

def download_nhk_video(target_url):
    match = re.search(r"das_id=([A-Z0-9_]+)", target_url)
    if not match:
        print("エラー: URLからdas_idが見つかりませんでした。")
        return
    das_id = match.group(1)

    cookie_dict, ffmpeg_cookie = load_cookies_from_txt()
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    
    common_headers = {
        "User-Agent": ua,
        "Referer": "https://www3.nhk.or.jp/",
        "Origin": "https://www3.nhk.or.jp",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8"
    }

    print(f"\n[{das_id}] 処理を開始します...")

    # 1. APIから動画パス取得 (エラー内容を詳細に出力するように修正)
    api_url = f"https://noaapi.web.nhk/r1/movies/?dasId={das_id}&_source=encodings"
    try:
        api_res = requests.get(api_url, headers=common_headers, cookies=cookie_dict, timeout=10)
        api_res.raise_for_status()
        path_match = re.search(r'"contentPath"\s*:\s*"([^"]+)"', api_res.text)
        if not path_match:
            print("エラー: JSON内に 'contentPath' が見つかりませんでした。")
            print(f"レスポンス内容: {api_res.text[:200]}")
            return
        base_path = re.sub(r'\.[a-zA-Z0-9]+$', '', path_match.group(1))
        print(f"動画パス取得成功: {base_path}")
    except Exception as e:
        print(f"❌ API情報取得失敗: {e}")
        if 'api_res' in locals():
            print(f"サーバーの返答: {api_res.text[:200]}")
        print("※Cookieの期限切れ、またはアクセス過多による一時的な制限の可能性があります。")
        return

    # 2. トークン取得 (こちらも詳細化)
    token_url = "https://mediatoken.web.nhk/v1/token"
    try:
        token_res = requests.get(token_url, headers=common_headers, cookies=cookie_dict, timeout=10)
        token_res.raise_for_status()
        token = token_res.json().get("token", "")
        print("トークン取得成功。")
    except Exception as e:
        print(f"❌ トークン取得失敗: {e}")
        if 'token_res' in locals():
            print(f"サーバーの返答: {token_res.text[:200]}")
        return

    # 3. URL構築とダウンロード
    m3u8_url = f"https://media.vd.st.nhk{base_path}/index.m3u8?hdnts={token}"
    output_file = f"{das_id}.mp4"

    ffmpeg_headers = f"User-Agent: {ua}\r\nReferer: https://www3.nhk.or.jp/\r\nOrigin: https://www3.nhk.or.jp\r\nCookie: {ffmpeg_cookie}\r\n"

    cmd = [
        "ffmpeg", "-hide_banner",
        "-headers", ffmpeg_headers,
        "-analyzeduration", "10000000",
        "-probesize", "10000000",
        "-i", m3u8_url,
        "-c", "copy",
        "-y", output_file
    ]

    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
    
    total_duration_sec = 0.0
    total_duration_str = "??:??:??"

    for line in process.stderr:
        if total_duration_sec == 0.0:
            dur_match = re.search(r"Duration:\s*(\d{2}:\d{2}:\d{2}\.\d{2})", line)
            if dur_match:
                total_duration_str = dur_match.group(1)[:8]
                total_duration_sec = time_to_seconds(dur_match.group(1))

        time_match = re.search(r"time=(\d{2}:\d{2}:\d{2}\.\d{2})", line)
        if time_match:
            current_time_str = time_match.group(1)[:8]
            current_sec = time_to_seconds(time_match.group(1))

            if total_duration_sec > 0:
                percent = (current_sec / total_duration_sec) * 100
                percent = min(percent, 100.0)
                bar_length = 20
                filled_length = int(bar_length * percent // 100)
                bar = "█" * filled_length + "░" * (bar_length - filled_length)
                sys.stdout.write(f"\r[{das_id}] 📥 DL中: [{bar}] {percent:.1f}% ({current_time_str} / {total_duration_str})")
                sys.stdout.flush()
            else:
                sys.stdout.write(f"\r[{das_id}] 📥 DL中: {current_time_str} 取得済み...")
                sys.stdout.flush()

    process.wait()
    
    if process.returncode == 0:
        print(f"\n[{das_id}] ✅ 完了: {output_file} に保存しました！\n")
    else:
        print(f"\n[{das_id}] ❌ エラー: ffmpegが異常終了しました (コード: {process.returncode})\n")

if __name__ == "__main__":
    url = input("NHK URLを入力してください: ")
    download_nhk_video(url)