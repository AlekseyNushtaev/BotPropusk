from dotenv import load_dotenv
import os

load_dotenv()

TG_TOKEN = os.environ.get("TG_TOKEN")
PAGE_SIZE = int(os.environ.get("PAGE_SIZE"))
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS").split()}
MAX_TRUCK_PASSES = int(os.environ.get("MAX_TRUCK_PASSES"))
MAX_CAR_PASSES = int(os.environ.get("MAX_CAR_PASSES"))
PASS_TIME = int(os.environ.get("PASS_TIME"))
RAZRAB = int(os.environ.get("RAZRAB"))
