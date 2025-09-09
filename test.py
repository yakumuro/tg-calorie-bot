import os
from dotenv import load_dotenv
from config.config import DATABASE_PATH

load_dotenv()

test = DATABASE_PATH
print(test)