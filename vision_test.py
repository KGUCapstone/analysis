from google.cloud import vision
from PIL import Image, ImageEnhance
import io,os,re


def text_extract(img_path):

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "service-account.json"

    # 이미지 전처리 (Pillow로 불러와 선명도 조정)
    pil_image = Image.open(img_path)

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

    if texts:
        print("전체 텍스트:\n", texts[0].description)
    else:
        print("텍스트가 감지되지 않았습니다.")

    return texts


def text_analyze(texts):
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


if __name__ == "__main__":
    img_path = "img/img.png"
    texts = text_extract(img_path)
    
    res = text_analyze(texts)
    product_name,price,volume,brand = res

    print("\n추출 결과:")
    print("상품명:", product_name or "없음")
    print("가격:", price or "없음")
    print("용량:", volume or "없음")
    print("브랜드:", brand or "없음")