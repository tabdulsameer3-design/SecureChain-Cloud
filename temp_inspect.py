import os
from app import create_app
from config import Config
from app.models import File
app = create_app(Config)
with app.app_context():
    files = File.query.all()
    print('files count', len(files))
    for f in files:
        print(f.id, f.original_filename, f.file_path, os.path.exists(f.file_path))
