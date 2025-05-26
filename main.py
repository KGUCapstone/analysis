from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import vision
from PIL import Image, ImageEnhance
import io, os, re, json, requests

app = FastAPI(title="가격표 이미지 분석 API")

backend_url = os.environ.get("BACKEND_URL", "http://localhost:8080")
frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:3000")

# CORS 설정 
app.add_middleware(
    CORSMiddleware,
    allow_origins=[backend_url, frontend_url],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 Google 서비스 계정 설정"""
    # 환경 변수에서 서비스 계정 JSON 가져오기
    service_account_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    
    if service_account_json:
        # 환경 변수의 내용을 파일로 저장
        with open("temp_service_account.json", "w") as f:
            f.write(service_account_json)
        
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_service_account.json"
    else:
        # 로컬 개발 환경용 
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account.json"




def text_extract(image_content):

    #os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account.json"

    # 이미지 전처리 (바이트에서 Pillow로 변환)
    #pil_image = Image.open(image_content)
    pil_image = Image.open(io.BytesIO(image_content))
    
    # 대비 향상 + 리사이즈
    enhanced_img = ImageEnhance.Contrast(pil_image).enhance(2.0)
    resized_img = enhanced_img.resize((pil_image.width * 2, pil_image.height * 2))
    
    # 이미지 -> 바이트로 변환 (Vision API가 읽을 수 있게게)
    img_byte_arr = io.BytesIO()
    resized_img.save(img_byte_arr, format='PNG')
    content = img_byte_arr.getvalue()
    
    # Vision API로 OCR
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=content)
    
    response = client.text_detection(image=image)
    texts = response.text_annotations
    #print(texts)
    return texts

# def text_analyze(texts):
#     if not texts:
#         return None, None, None, None
        
#     full_text = texts[0].description
#     lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
#     product_name = None
#     price = None
#     volume = None
#     brand = None
    
#     brand_keywords = ['청정원', '오뚜기', 'CJ', '풀무원', '해표', '샘표', '롯데', '대상']
    
#     volume_pattern = re.compile(r'\d+\s?(ml|g|kg|L|ℓ)', re.IGNORECASE)
#     price_pattern = re.compile(r'^\d{1,3}(,\d{3})+$|^\d+$')
    
#     candidates = []
    
#     for line in lines:
#         # 단위 가격 줄은 무시시
#         if '당' in line or 'g당' in line or 'ml당' in line or '당 ' in line:
#             continue
        
#         # 기존 브랜드에서 찾기
#         if not brand:
#             for keyword in brand_keywords:
#                 if keyword in line:
#                     brand = keyword
#                     break
        
#         # 용량
#         if not volume:
#             volume_match = volume_pattern.search(line)
#             if volume_match:
#                 volume = volume_match.group()
        
#         # 가격
#         if not price:
#             if '원' in line:
#                 match = re.search(r'(\d{1,3}(,\d{3})+|\d+)\s*원', line)
#                 if match:
#                     price = match.group()
#             elif price_pattern.match(line) and len(line) <= 6:
#                 price = line
        
#         # 바코드 제외
#         if re.fullmatch(r'\d{13}', line):
#             continue
        
#         # 상품명 후보
#         if (brand and brand in line) or (volume and volume in line):
#             candidates.append(line)
    
#     # 상품명 결정
#     if candidates:
#         product_line = max(candidates, key=len)
#         product_line = product_line.replace(brand or "", "").replace(volume or "", "")
#         product_name = product_line.strip(")- (")
    
#     return product_name, price, volume, brand


def text_analyze(texts):
    if not texts:
        print("[디버깅] OCR 결과 없음")
        return None, None, None, None
        
    full_text = texts[0].description
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    #print(f"[디버깅] 전체 OCR 라인:\n{lines}\n")

    product_name = None
    price = None
    volume = None
    brand = None

    brand_keywords = ['청정원', '오뚜기', 'CJ', '풀무원', '해표', '샘표', '롯데', '대상', '해태', '크라운', '오리온', '동원']
    volume_pattern = re.compile(r'(\d+\.?\d*)\s?(ml|g|kg|L|ℓ|G)', re.IGNORECASE)
    
    # 가격 패턴
    main_price_patterns = [
        re.compile(r'(\d{1,3},\d{3})'),
        re.compile(r'(\d{1,3}\s*,\s*\d{3})'),
    ]
    price_patterns = [
        re.compile(r'(\d{1,3}(,\d{3})+)\s*원?'),
        re.compile(r'(\d+)\s*원'),
    ]
    
    barcode_pattern = re.compile(r'^\d{12,14}$')
    date_pattern = re.compile(r'\d{4}[./-]\d{2}[./-]?\d{0,2}')
    price_candidates = []
    candidates = []

    for line in lines:
        print(f"[디버깅] 라인 분석: {line}")

        # 바코드/날짜/이벤트 용어 제거
        if barcode_pattern.match(line) or date_pattern.search(line):
            print("[제외] 바코드 또는 날짜 형식 감지")
            continue
        if any(tag in line for tag in ['행사상품', '행사기간', '단위가격', '기준']):
            print("[제외] 무의미한 키워드 포함")
            continue
        if re.search(r'^\d{2,3}\s*,?\d{3}$', line):  # 숫자만 있는 줄 (가격과 중복 가능)
            continue

        # 브랜드 검출
        if not brand:
            for keyword in brand_keywords:
                if keyword in line:
                    brand = keyword
                    print(f"[감지] 브랜드: {brand}")
                    break

        # 용량 검출
        if not volume:
            volume_match = volume_pattern.search(line)
            if volume_match:
                volume = volume_match.group()
                print(f"[감지] 용량: {volume}")

        # 가격 감지 - 높은 우선순위
        for pattern in main_price_patterns:
            match = pattern.search(line)
            if match:
                value = match.group(1).replace(" ", "")
                price_candidates.append((value, 20))
                print(f"[감지] 주요 가격 후보: {value}")
                break

        # 가격 감지 - 일반 우선순위
        for pattern in price_patterns:
            match = pattern.search(line)
            if match:
                value = match.group(1).replace(",", "")
                if value.isdigit() and 500 <= int(value) <= 100000:
                    price_candidates.append((value, 5))
                    print(f"[감지] 일반 가격 후보: {value}")
                break

        # 상품명 후보 - 한글 포함, 너무 짧거나 숫자 위주 제외
        if len(line) > 3 and re.search(r'[가-힣]', line) and not line.isdigit():
            candidates.append(line)
            print(f"[후보] 상품명 후보 추가: {line}")
    
    # 가격 결정
    if price_candidates:
        price_candidates.sort(key=lambda x: x[1], reverse=True)
        price = price_candidates[0][0]
        if len(price) >= 4 and ',' not in price:
            price = price[:-3] + ',' + price[-3:]
        price = price + "원"
        print(f"[선택] 최종 가격: {price}")
    
    # # 상품명 결정
    # if candidates:
    #     filtered = [c for c in candidates if (brand and brand in c) or (volume and volume in c)]
    #     product_line = max(filtered, key=len) if filtered else max(candidates, key=len)
    #     if brand:
    #         product_line = product_line.replace(brand, "")
    #     if volume:
    #         product_line = product_line.replace(volume, "")
    #     product_name = product_line.strip("- )(")
    #     print(f"[선택] 최종 상품명: {product_name}")
    # 상품명 결정
    if candidates:
        filtered = [c for c in candidates if (brand and brand in c) or (volume and volume in c)]
        product_line = max(filtered, key=len) if filtered else max(candidates, key=len)
        
        if brand:
            product_line = product_line.replace(brand, "")
        if volume:
            product_line = product_line.replace(volume, "")
        
        # 불필요한 괄호/기호 제거
        product_name = product_line.strip("- )(").strip()
        
        # brand가 괄호로 감싸진 형태로 product_name에 포함되었을 때 추가 정리
        if product_name.startswith(")") or product_name.endswith(")"):
            product_name = product_name.strip(")")
        if product_name.startswith("("):
            product_name = product_name.strip("(")
    
    print(f"\n[결과] 상품명: {product_name}, 가격: {price}, 용량: {volume}, 브랜드: {brand}\n")
    return product_name, price, volume, brand



def result(img_path):
    texts = text_extract(img_path)
    product_name, price, volume, brand = text_analyze(texts)

    def parse_price(price_str):
        if not price_str:
            return 0
        try:
            return int(price_str.replace(",", "").replace("원", "").strip())
        except:
            return 0

    price_num = parse_price(price)

    if not product_name:
        print("no")
    else: 
        payload = {
            "title": product_name or "",
            "price": price_num if price_num is not None else 0,
            "volume": volume or "",
            "brand": brand or ""
        }
        #print(payload)
        return payload  
    
@app.get("/")
async def root():
    return {"message": "상품 이미지 분석 API."}

@app.post("/analyze/")
async def analyze_image(file: UploadFile = File(...)):
    image_content = await file.read()

    try:
        return result(image_content)
    
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": f"오류 발생: {str(e)}"}
        )
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

