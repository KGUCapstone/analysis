from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import vision
from PIL import Image, ImageEnhance
import io, os, re, json

app = FastAPI(title="상품 이미지 분석 API")

# CORS 설정 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
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
    # 이미지 전처리 (바이트에서 Pillow로 변환)
    pil_image = Image.open(io.BytesIO(image_content))
    
    # 대비 향상 + 리사이즈
    enhanced_img = ImageEnhance.Contrast(pil_image).enhance(2.0)
    resized_img = enhanced_img.resize((pil_image.width * 2, pil_image.height * 2))
    
    # 이미지 → 바이트로 변환 (Vision API가 읽을 수 있도록)
    img_byte_arr = io.BytesIO()
    resized_img.save(img_byte_arr, format='PNG')
    content = img_byte_arr.getvalue()
    
    # Vision API로 OCR
    client = vision.ImageAnnotatorClient()
    image = vision.Image(content=content)
    
    response = client.text_detection(image=image)
    texts = response.text_annotations
    
    return texts

def text_analyze(texts):
    if not texts:
        return None, None, None, None
        
    full_text = texts[0].description
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    product_name = None
    price = None
    volume = None
    brand = None
    
    brand_keywords = ['청정원', '오뚜기', 'CJ', '풀무원', '해표', '샘표', '롯데', '대상']
    
    volume_pattern = re.compile(r'\d+\s?(ml|g|kg|L|ℓ)', re.IGNORECASE)
    price_pattern = re.compile(r'^\d{1,3}(,\d{3})+$|^\d+$')
    
    candidates = []
    
    for line in lines:
        # 단위 가격 줄은 건너뜀
        if '당' in line or 'g당' in line or 'ml당' in line or '당 ' in line:
            continue
        
        # 기존 브랜드에서 찾기
        if not brand:
            for keyword in brand_keywords:
                if keyword in line:
                    brand = keyword
                    break
        
        # 용량
        if not volume:
            volume_match = volume_pattern.search(line)
            if volume_match:
                volume = volume_match.group()
        
        # 가격
        if not price:
            if '원' in line:
                match = re.search(r'(\d{1,3}(,\d{3})+|\d+)\s*원', line)
                if match:
                    price = match.group()
            elif price_pattern.match(line) and len(line) <= 6:
                price = line
        
        # 바코드 제외
        if re.fullmatch(r'\d{13}', line):
            continue
        
        # 상품명 후보
        if (brand and brand in line) or (volume and volume in line):
            candidates.append(line)
    
    # 상품명 결정
    if candidates:
        product_line = max(candidates, key=len)
        product_line = product_line.replace(brand or "", "").replace(volume or "", "")
        product_name = product_line.strip(")- (")
    
    return product_name, price, volume, brand

@app.get("/")
async def root():
    return {"message": "상품 이미지 분석 API."}

@app.post("/analyze/")
async def analyze_image(file: UploadFile = File(...)):
    import requests

    image_content = await file.read()

    try:
        texts = text_extract(image_content)
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
            return JSONResponse(status_code=400, content={"message": "상품명을 찾을 수 없습니다."})

        payload = {
            "title": product_name or "",
            "price": price_num,
            "volume": volume or "",
            "brand": brand or ""
        }

        print("Spring으로 보낼 JSON:", payload)

        backend_url = os.environ.get("BACKEND_URL", "http://localhost:8080")
        headers = {"Content-Type": "application/json"}
        backend_response = requests.post(
            backend_url + "/api/shopping/search",
            headers=headers,
            json=payload
        )
        backend_response.raise_for_status()

        return backend_response.json()

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"message": f"오류 발생: {str(e)}"}
        )
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


