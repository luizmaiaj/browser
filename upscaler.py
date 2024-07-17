import os
import subprocess

def ensure_executable():
    os.chmod('realesrgan-ncnn-vulkan', 0o755)

def list_models():
    models = [f for f in os.listdir('models') if f.endswith('.bin')]
    return [model.replace('.bin', '') for model in models]

def enhance_image(input_path, output_path, model='realesr-animevideov3-x4', scale=1, fmt='png'):
    command = [
        './realesrgan-ncnn-vulkan',
        '-i', input_path,
        '-o', output_path,
        '-n', model,
        '-s', str(scale),
        '-f', fmt
    ]
    subprocess.run(command, check=True)

def enhance_anime_video(input_video, output_video, model='realesr-animevideov3-x2', scale=2):
    tmp_frames = 'tmp_frames'
    out_frames = 'out_frames'
    
    os.makedirs(tmp_frames, exist_ok=True)
    os.makedirs(out_frames, exist_ok=True)

    extract_frames_command = [
        'ffmpeg', '-i', input_video, '-qscale:v', '1', '-qmin', '1', '-qmax', '1', '-vsync', '0',
        os.path.join(tmp_frames, 'frame%08d.jpg')
    ]
    subprocess.run(extract_frames_command, check=True)

    enhance_frames_command = [
        './realesrgan-ncnn-vulkan',
        '-i', tmp_frames,
        '-o', out_frames,
        '-n', model,
        '-s', str(scale),
        '-f', 'jpg'
    ]
    subprocess.run(enhance_frames_command, check=True)

    merge_frames_command = [
        'ffmpeg', '-i', os.path.join(out_frames, 'frame%08d.jpg'), '-i', input_video,
        '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'copy', '-c:v', 'libx264', '-r', '23.98', '-pix_fmt', 'yuv420p',
        output_video
    ]
    subprocess.run(merge_frames_command, check=True)

def main():
    ensure_executable()

    models = list_models()
    print("Available models:")
    for i, model in enumerate(models, start=1):
        print(f"{i}. {model}")

    model_choice = int(input("Choose a model by number: ")) - 1
    chosen_model = models[model_choice]

    input_path = input("Enter the input file path: ").strip()
    output_path = f"out_{input_path}"

    file_extension = os.path.splitext(input_path)[1].lower()

    if file_extension in ['.jpg', '.jpeg', '.png']:
        scale = int(input("Enter the scale factor (e.g., 2, 3, 4): ").strip())
        fmt = file_extension.lstrip('.')
        enhance_image(input_path, output_path, chosen_model, scale, fmt)
    elif file_extension in ['.mp4', '.mkv', '.avi', '.mov']:
        scale = int(input("Enter the scale factor (e.g., 2, 3, 4): ").strip())
        enhance_anime_video(input_path, output_path, chosen_model, scale)
    else:
        print("Invalid file type. Please provide an image or video file.")

if __name__ == "__main__":
    main()