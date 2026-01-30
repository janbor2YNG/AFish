import random
import json

random.randint(10000,999999)
id = {"id": {random.randint(10000,999999)}}


with open('data.json', 'w') as outfile:
    json.dump({id})