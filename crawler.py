import os
import re
import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

TARGET_DISTRICTS = ["신안", "완도", "진도", "고흥", "해남", "영광", "서귀포", "추자", "우도", "대정", "성산"]
CORE_KEYWORDS = ["초등", "기간제", "교사"]
HOUSING_KEYWORDS = ["관사", "사택", "숙소", "원룸", "거주", "기숙사"]

def fetch_jeonnam():
    posts = []
    url = "https://www.jne.go.kr/main/na/ntt/selectNttList.do?mi=259&bbsId=104"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")
        
        for row in soup.find_all("tr"):
            link = row.find("a")
            if not link:
                continue
            
            title = link.get_text(strip=True)
            onclick = link.get("onclick", "")
            href = link.get("href", "")
            
            # 게시글 고유 식별 번호(nttSn) 추출
            sn_match = re.search(r"['\"]?(\d{5,8})['\"]?", onclick or href)
            if sn_match:
                ntt_sn = sn_match.group(1)
                detail_url = f"https://www.jne.go.kr/main/na/ntt/selectNttInfo.do?mi=259&bbsId=104&nttSn={ntt_sn}"
                post_id = f"jne_{ntt_sn}"
            else:
                if not href or href.startswith("javascript:"):
                    continue
                detail_url = href if href.startswith("http") else f"https://www.jne.go.kr{href}"
                post_id = f"jne_{abs(hash(detail_url))}"

            if not any(k in title for k in CORE_KEYWORDS):
                continue

            has_housing = any(k in title for k in HOUSING_KEYWORDS)
            matched_district = next((d for d in TARGET_DISTRICTS if d in title), "전남 기타")
            in_target = matched_district != "전남 기타"

            posts.append({
                "id": post_id,
                "title": title,
                "url": detail_url,
                "region": "전남",
                "district": matched_district,
                "has_housing_hint": has_housing,
                "in_target_district": in_target
            })
    except Exception as e:
        print(f"[전남교육청 수집 에러]: {e}")
    return posts

def fetch_jeju():
    posts = []
    url = "https://www.jje.go.kr/board/list.jje?boardId=BBS_0000041&menuCd=DOM_000000103001000000"
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        for row in soup.find_all("tr"):
            link = row.find("a")
            if not link:
                continue

            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not href or href.startswith("javascript:"):
                continue

            detail_url = href if href.startswith("http") else f"https://www.jje.go.kr{href}"
            
            sid_match = re.search(r"dataSid=(\d+)", href)
            data_sid = sid_match.group(1) if sid_match else str(abs(hash(detail_url)))
            post_id = f"jje_{data_sid}"

            if not any(k in title for k in CORE_KEYWORDS):
                continue

            has_housing = any(k in title for k in HOUSING_KEYWORDS)
            matched_district = next((d for d in TARGET_DISTRICTS if d in title), "제주 일반")
            in_target = matched_district != "제주 일반"

            posts.append({
                "id": post_id,
                "title": title,
                "url": detail_url,
                "region": "제주",
                "district": matched_district,
                "has_housing_hint": has_housing,
                "in_target_district": in_target
            })
    except Exception as e:
        print(f"[제주교육청 수집 에러]: {e}")
    return posts

def main():
    if not (SUPABASE_URL and SUPABASE_KEY):
        print("Supabase 환경 변수가 설정되지 않았습니다.")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. 사이트에서 공고 수집
    fetched = fetch_jeonnam() + fetch_jeju()
    if not fetched:
        print("수집된 공고가 없습니다.")
        return

    # 2. 이미 DB에 들어있는 공고 ID 확인
    existing_res = supabase.table("job_postings").select("id").execute()
    existing_ids = {row["id"] for row in existing_res.data}

    # 3. 새로운 공고만 필터링하여 DB에 삽입
    new_posts = [p for p in fetched if p["id"] not in existing_ids]

    if new_posts:
        print(f"신규 공고 {len(new_posts)}건 발견. DB 적재 진행...")
        supabase.table("job_postings").insert(new_posts).execute()
        print("DB 업데이트 완료.")
    else:
        print("새로운 공고가 없습니다.")

if __name__ == "__main__":
    main()
