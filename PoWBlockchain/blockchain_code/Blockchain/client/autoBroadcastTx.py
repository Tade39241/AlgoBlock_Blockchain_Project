import requests
import time
import random
from Blockchain.Backend.core.database.db import AccountDB

fromAccount = "1ALbtk4ocsg2Qb67aiZRegL5sdhQ1gW7FD"

""" Read all the accounts """
AllAccounts = AccountDB().read()

def autoBroadcast():
    while True:
        for account in AllAccounts:
            if account[0]["public_addr"] != fromAccount:
                paras = {"fromAddress": fromAccount,
                        "toAddress": account[0]["public_addr"],
                        "Amount": random.randint(1,35)}

                res = requests.post(url ="http://localhost:5900/wallet", data = paras)   
        time.sleep(3)