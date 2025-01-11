import cv2
import numpy as np
import os
from fpdf import FPDF
from PIL import Image

def is_roi_blank(roi_gray, blank_threshold=10):
    std_dev = np.std(roi_gray)
    return std_dev < blank_threshold

def save_roi_image(roi_frame, output_dir, frame_index):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    img_name = f"score_{frame_index:06d}.png"
    img_path = os.path.join(output_dir, img_name)
    cv2.imwrite(img_path, roi_frame)
    print(f"[擷取] 已儲存：{img_path}")
    return img_path

def find_sheet_bottom(image, height, width):
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    btm = int(height / 2)
    for h in range(btm-1, 0, -1):
        row_sum = int(np.sum(gray_image[h].astype(np.int32)))
        if row_sum / width > 210:
            btm = h
            break
    return int(btm)

def capture_scores_from_video(video_path, roi=(0, 0, 640, 100), threshold=30, min_frames_gap=10, start_time=None, end_time=None, skip_blank=True, blank_threshold=10, output_dir="captures"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("無法開啟影片：", video_path)
        return []

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if start_time is not None:
        start_frame = int(start_time * fps)
    else:
        start_frame = 0

    if end_time is not None:
        end_frame = int(end_time * fps)
        end_frame = min(end_frame, total_frames)
    else:
        end_frame = total_frames

    x, y, _, _ = roi
    image_paths = []
    prev_rect, now_rect = -999, -999
    interval = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        h = int(find_sheet_bottom(frame, height, w))

        current_frame = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

        if current_frame > end_frame:
            break

        if current_frame < start_frame:
            continue

        roi_frame = frame[y:y+h, x:x+w]

        gray_image, light_gray_mask, deep_gray_mask, selected_area = found_boundary(roi_frame)
        start_rect = selected_area[0]
        
        if start_rect == w and interval <= 400:
            interval += 1
            continue

        elif prev_rect < 0 or (start_rect + 100) < prev_rect or interval > 400:
            roi_frame = filter_roi_image(gray_image, light_gray_mask, deep_gray_mask, selected_area)
            img_path = save_roi_image(roi_frame, output_dir, current_frame)
            image_paths.append(img_path)
            interval = 0

        interval += 1
        prev_rect = start_rect

    cap.release()
    return image_paths

class PDFWithScores(FPDF):
    def __init__(self, margin=10):
        super().__init__()
        self.margin = margin
        self.current_y = margin

    def add_score(self, image_path, max_width=190):
        img = Image.open(image_path)
        img_width, img_height = img.size
        scale = max_width / img_width
        display_w = max_width
        display_h = img_height * scale
        page_height = 297
        available_height = page_height - self.current_y - self.margin
        if display_h > available_height:
            self.add_page()
            self.current_y = self.margin
        self.image(image_path, x=self.margin, y=self.current_y, w=display_w)
        self.current_y += display_h

def create_pdf_with_multiple_scores(image_paths, output_pdf="output.pdf"):
    pdf = PDFWithScores(margin=10)
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    for img_path in image_paths:
        pdf.add_score(img_path, max_width=190)
    pdf.output(output_pdf)
    print(f"[完成] PDF 輸出：{output_pdf}")

def found_boundary(image):
    height, width, _ = image.shape
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    lower_deep_gray = 40
    upper_deep_gray = 100
    lower_light_gray = 160
    upper_light_gray = 216
    deep_gray_mask = cv2.inRange(gray_image, lower_deep_gray, upper_deep_gray)
    light_gray_mask = cv2.inRange(gray_image, lower_light_gray, upper_light_gray)
    w = [0] * width
    h = [0] * height
    for i in range(0, height):
        for j in range(0, width):
            if light_gray_mask[i][j] > 0:
                w[j] += 1
                h[i] += 1
    filtered_w = [id for id, count in enumerate(w) if count > 105]
    filtered_h = [id for id, count in enumerate(h) if count > 100]
    if filtered_w:
        min_w = min(filtered_w)
        max_w = max(filtered_w)
    else:
        min_w = width
        max_w = 0
    if filtered_h:
        min_h = min(filtered_h)
        max_h = max(filtered_h)
    else:
        min_h = height
        max_h = 0
    selected_area = [min_w, max_w, min_h, max_h]
    return gray_image, light_gray_mask, deep_gray_mask, selected_area

def filter_roi_image(gray_image, light_gray_mask, deep_gray_mask, selected_area):
    min_w, max_w, min_h, max_h = selected_area
    for dh in range(min_h, max_h):
        for dw in range(min_w, max_w):
            if light_gray_mask[dh][dw] > 0:
                gray_image[dh][dw] = 255
            elif deep_gray_mask[dh][dw] > 0:
                gray_image[dh][dw] = 0
    result = cv2.cvtColor(gray_image, cv2.COLOR_GRAY2BGR)
    cv2.rectangle(result, (min_w, min_h), (max_w, max_h), color=(0, 255, 0), thickness=1)    
    return result

def main():
    video_path = "videos/piano.mp4"
    roi = (0, 0, 1700, 168)
    threshold = 50
    min_frames_gap = 20
    start_time = 10
    end_time = 276
    skip_blank = True
    blank_threshold = 10
    output_dir = "captures"
    image_paths = capture_scores_from_video(
        video_path=video_path,
        roi=roi,
        threshold=threshold,
        min_frames_gap=min_frames_gap,
        start_time=start_time,
        end_time=end_time,
        skip_blank=skip_blank,
        blank_threshold=blank_threshold,
        output_dir=output_dir
    )
    if not image_paths:
        print("沒有擷取到任何樂譜圖片，請檢查影片或參數設定。")
        return
    output_pdf = "multi_score_output.pdf"
    create_pdf_with_multiple_scores(image_paths, output_pdf=output_pdf)

if __name__ == "__main__":
    main()
