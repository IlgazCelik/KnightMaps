import os
import cv2

def extract_frames(video_path, output_dir="dataset", interval=40):
    os.makedirs(output_dir, exist_ok=True)
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return
    
    frame_count = 0
    saved_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_count % interval == 0:
            image_path = os.path.join(output_dir, f"frame_{frame_count:06d}.jpg")
            cv2.imwrite(image_path, frame)
            saved_count += 1
            
        frame_count += 1
        
    cap.release()
    print(f"Successfully processed! Saved {saved_count} frames to the '{output_dir}' folder.")

if __name__ == "__main__":
    input_video_path = "input.mp4"
    extract_frames(input_video_path, output_dir="dataset", interval=40)