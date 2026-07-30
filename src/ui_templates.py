import os

from fastapi.templating import Jinja2Templates

from src.i18n import get_text

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(templates_dir, exist_ok=True)
templates = Jinja2Templates(directory=templates_dir)
templates.env.globals["t"] = get_text
