import os
import zipfile

def package_roku_app(source_dir, output_zip):
    print(f"Packaging {source_dir} -> {output_zip}...")
    if os.path.exists(output_zip):
        os.remove(output_zip)
    
    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_dir):
            for file in sorted(files):
                # Ignore system / editor files
                if file.startswith('.') or file.endswith('.tmp'):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_dir)
                # CRITICAL for Roku OS: Paths must use forward slash '/'
                arcname = rel_path.replace('\\', '/')
                zf.write(full_path, arcname)
    
    # Verify entries in created zip
    with zipfile.ZipFile(output_zip, 'r') as zf:
        entries = zf.namelist()
        has_manifest = 'manifest' in entries
        has_backslash = any('\\' in name for name in entries)
        print(f"  [OK] {len(entries)} entries, Manifest at root: {has_manifest}, Backslashes: {has_backslash}, Size: {os.path.getsize(output_zip):,} bytes")

if __name__ == '__main__':
    base_dir = os.path.dirname(os.path.abspath(__file__))
    apps = [
        ('roku-streaming-hub', 'roku-streaming-hub.zip'),
        ('roku-famelack', 'famelack.zip'),
        ('roku-moviebox', 'moviebox.zip'),
        ('roku-fbstream', 'fbstream.zip'),
    ]
    for src, out in apps:
        src_path = os.path.join(base_dir, src)
        out_path = os.path.join(base_dir, out)
        if os.path.isdir(src_path):
            package_roku_app(src_path, out_path)
    print("\nAll packages created successfully!")
