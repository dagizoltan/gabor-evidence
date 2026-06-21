import os
from PIL import Image

def convert_images(root_dir='.'):
    # Supported input extensions to be converted to .jpg
    input_extensions = ('.png', '.jpeg')

    for subdir, dirs, files in os.walk(root_dir):
        # Filter for files with target extensions
        image_files = [f for f in files if f.lower().endswith(input_extensions)]

        for filename in image_files:
            filepath = os.path.join(subdir, filename)
            try:
                with Image.open(filepath) as img:
                    # Handle transparency by compositing onto a white background
                    if img.mode in ("RGBA", "P"):
                        # Create a white background image
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        # Paste the image onto the background using the alpha channel as a mask
                        if img.mode == "RGBA":
                            background.paste(img, (0, 0), img)
                        else:
                            background.paste(img.convert("RGBA"), (0, 0), img.convert("RGBA"))
                        img = background
                    elif img.mode != "RGB":
                        img = img.convert("RGB")

                    # Determine output filename with .jpg extension
                    base = os.path.splitext(filepath)[0]
                    output_filename = f"{base}.jpg"

                    # Save as JPEG with high quality
                    img.save(output_filename, "JPEG", quality=95)
                    print(f"Successfully converted: {filepath} -> {output_filename}")

                # Delete the original file after successful conversion
                os.remove(filepath)
                print(f"Removed original file: {filepath}")

            except Exception as e:
                print(f"Error processing {filepath}: {e}")

if __name__ == "__main__":
    convert_images()
