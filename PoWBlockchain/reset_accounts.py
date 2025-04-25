#!/usr/bin/env python3
"""
Reset Account and Blockchain State for PoS Blockchain Testing

This script will:
  - Backup your account and blockchain databases (if they exist)
  - Recreate the account table with the hardcoded test ACCOUNTS.
  - Optionally, back up and reset the blockchain state.
  
Usage:
  python reset_accounts.py --reset-blockchain   (to reset blockchain state too)
"""

import os
import re
import sys
import sqlite3
import json
import time
import logging
import argparse

from datetime import datetime
# Set your project root
PROJECT_ROOT = "/Users/tadeatobatele/Documents/UniStuff/CS351 Project/code/PoSBlockchain"

# Hardcoded test accounts
ACCOUNTS = {
    "1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig": {
        "privateKey": 96535626569238604192129746772702330856431841702880282095447645155889990991526, 
        "public_addr": "1DPPqS7kQNQMcn28du4sYJe8YKLUH8Jrig", 
        "public_key": "0248c103d04cc26840fa000d9614301fa5aee9d79b3a972e61c0712367658530b4", 
        "staked": 100 * 100000000,         # becomes 10000000000
        "unspent": 100 * 100000000,            
        "locked_until": 0, 
        "staking_history": "[]"
    },
    "14yikjhubj1sepvqsvzpRv4H6LhMN43XGD": {
        "privateKey": 101116694282830344663754055609096743199644277746685645606199809457638491163865, 
        "public_addr": "14yikjhubj1sepvqsvzpRv4H6LhMN43XGD", 
        "public_key": "0387c964aa67e33f0b93d3221b1bdfce382746cc7772e7497ca2677826f58d901d", 
        "staked": 100 * 100000000,
        "unspent": 100 * 100000000, 
        "locked_until": 0, 
        "staking_history": "[]"
    },
    "1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz": {
        "privateKey": 46707185248865296345366463593339102785859545093537333336358754291775493830931, 
        "public_addr": "1Lu9SwPPo7DJYrMVrZnkDXVw5y4aEeF1kz", 
        "public_key": "035b605b121b0382b340dd55bb960bd73c19bb5b484d61837b41beb29b1e8341b1", 
        "staked": 100 * 100000000,
        "unspent": 100 * 100000000, 
        "locked_until": 0, 
        "staking_history": "[]"
    },
    "1NXxqHLLCScgr1iHF1UDK321suUuDwGRPm": {
        "privateKey": 34000324781627639488158959741135997485464801084950355524793577860707372017411,
        "public_addr": "1NXxqHLLCScgr1iHF1UDK321suUuDwGRPm",
        "public_key": "03f4035816dc437326137bf285d3bb5b835de2d1bcd18491ceb56bd4ab3b889425",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1GxVzm78RwEvFVv3o5XDoXRiRZhB3W6yc6": {
        "privateKey": 66026761182332030715725330936737920463055154345934239366259156690961890180432,
        "public_addr": "1GxVzm78RwEvFVv3o5XDoXRiRZhB3W6yc6",
        "public_key": "03608d2b3d2828df70e68f95a6f95f1f6c8dd94dd4875ebc539ec56e5d768b8571",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1BfRrnvKHFB9Z2v8MQ9qZADDZUVM8i1vu7": {
        "privateKey": 224209144175479227881776260137908389369527090860163122908962184178388407532,
        "public_addr": "1BfRrnvKHFB9Z2v8MQ9qZADDZUVM8i1vu7",
        "public_key": "0250130170fde3938c4aed30628a331f5cd01a5dac6bdb2fbf4ae77773456d0f9e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "19owxqJs4N8PD8E9VXyVYA9yDr8EYaY1UC": {
        "privateKey": 99055237491890936310203650836741805944968814010051858867862678105493904648038,
        "public_addr": "19owxqJs4N8PD8E9VXyVYA9yDr8EYaY1UC",
        "public_key": "0336a74e18525ac1ae6e7ac00864afb07dc9a799cae38e14d45fe8f1c2d6189a0d",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1MAGrSBGsQPEC5ioAuc1WWkTNfiUbPJHiE": {
        "privateKey": 7803541504162869268647070319162388620502706065419320971530348509082754553563,
        "public_addr": "1MAGrSBGsQPEC5ioAuc1WWkTNfiUbPJHiE",
        "public_key": "03c4e0a95e2fe855bd660ec4f0dd5d36cdf039f14b8ae9db430a794d4f9a2dcf45",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Q4GjeDraAXjANioicEPpPHQSwfnANCAge": {
        "privateKey": 108950488652529291216916277044750894381204710390177740411395979619432757671424,
        "public_addr": "1Q4GjeDraAXjANioicEPpPHQSwfnANCAge",
        "public_key": "02964d4a53c698fa744f2a82c5a5e2a847bc2f00d88e1e603654bc95aa40b30e3d",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1N1iy92EaHLhhm2Gou1eLf3wstsAihgjq5": {
        "privateKey": 8564554150087408065324564847779753065153100539074815877094943530026730292866,
        "public_addr": "1N1iy92EaHLhhm2Gou1eLf3wstsAihgjq5",
        "public_key": "0242d77a5c5857fb4925c038d78ed8c2415c050568d439c4c38647c7db17be3b1a",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "15S85ymTY7HsfRvksDwqKZH8KWhHrL537S": {
        "privateKey": 63089788017224305673845170102074734930175609743972976485395847306744847351685,
        "public_addr": "15S85ymTY7HsfRvksDwqKZH8KWhHrL537S",
        "public_key": "023e5393d0989c8011a53b096ab900304c73bc54081f5449d9420e81ed81d428c3",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "132cwiEfHNVuXqqJ4zPuCqoRTUr9wGz3nE": {
        "privateKey": 25167093217950657608124868392723185222729233883196948120758689737316302455919,
        "public_addr": "132cwiEfHNVuXqqJ4zPuCqoRTUr9wGz3nE",
        "public_key": "03b1ae86f1e223b336ab406a25dc7a456b2e06db5da7f34236f16669dc56eb3b15",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "15o21d52GkGSYDvdPX4kZQT34VpyLBenzj": {
        "privateKey": 366473305681932944776276978140376549437432103449419970254383947756156799563,
        "public_addr": "15o21d52GkGSYDvdPX4kZQT34VpyLBenzj",
        "public_key": "02bdabe52a18f565cb3393ea6a75ab22c572cb101bf7babec88040129289d5a5d2",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Kdw22RFnfA3pUG6LVXxUSGz5K6Qm1LiCP": {
        "privateKey": 68196237506888735759706549688683157064913484545722069016841953509095084163341,
        "public_addr": "1Kdw22RFnfA3pUG6LVXxUSGz5K6Qm1LiCP",
        "public_key": "0304a8eed852d1e5943fd1880778ad5b367e71270234e5535c15f095f4774c80fb",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1E2AMZxYKrcq1BQA95dwg2di1Mi9VujZEw": {
        "privateKey": 12772964749162889793335928629227407208776674404294852083043649758795463192153,
        "public_addr": "1E2AMZxYKrcq1BQA95dwg2di1Mi9VujZEw",
        "public_key": "030c864ae9c0925d3d7286af405177583af3b0b8a0eff518503b109d4dc2f7d911",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1LBQuhbzAyK11SynY1NL6AwZVdQyNHaRTJ": {
        "privateKey": 85187119590840226482253265894196150749341284436904153245798812684918589467285,
        "public_addr": "1LBQuhbzAyK11SynY1NL6AwZVdQyNHaRTJ",
        "public_key": "026fa06f94540ac0041f77e74a4d6130fd935fd33be17b831794f5b1f7e8700b2e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1N64yCxu14UiFDFrt9Rtt9Dw992SMv6hwc": {
        "privateKey": 87503937509663859852631126467036228976192670550887448999819338294945059348863,
        "public_addr": "1N64yCxu14UiFDFrt9Rtt9Dw992SMv6hwc",
        "public_key": "022d37af29d1bd59e2aa8320b367e1c86bf219a2834975aa8e5ca42a6ee787a79a",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1GKU6DStGUEcXiQ9mE5wSmxF2ZFA373oSk": {
        "privateKey": 114333931291218278272426383903642540677865945046961483051964385706330508115153,
        "public_addr": "1GKU6DStGUEcXiQ9mE5wSmxF2ZFA373oSk",
        "public_key": "03d6a470994ff25fc76e286fd14c506cfe29d84d14148d3cf1065d6116699aefe5",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Gj6UrEHro7ggNU61WPPQDwVZKtftgArdY": {
        "privateKey": 62869410552546723444175557742109948879308039129704718485396153645499915608524,
        "public_addr": "1Gj6UrEHro7ggNU61WPPQDwVZKtftgArdY",
        "public_key": "02e9d9002a4c43e3e4605cd87a9f19adf9e51ebb3f68a6536de2eb92564712b4e0",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Ae3femn9CLSb4wTHNnxNV54ngjWEKrsyr": {
        "privateKey": 50487472671103539148391542521562077047552631621042892992011793769223068332368,
        "public_addr": "1Ae3femn9CLSb4wTHNnxNV54ngjWEKrsyr",
        "public_key": "0277a2f3067fa8cd250169286f5bdf4b47928eb2dd00f8b0d9052d5314162281bc",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1HSZX7eSgQfijUGKa1G3ZntwYN19n7Wg9E": {
        "privateKey": 7735480742185874618418368449258224302364917965810375487656269052979108327167,
        "public_addr": "1HSZX7eSgQfijUGKa1G3ZntwYN19n7Wg9E",
        "public_key": "039a94f43ec88b2d9db3f980b6403dd276e3229a6e24504ec93209a113e0d5175e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "12mqu6yCW3hKsnRkZPer7WoHK92xfj5zKL": {
        "privateKey": 26661305183494202854535091623406057463398387869097086576536697864329468263760,
        "public_addr": "12mqu6yCW3hKsnRkZPer7WoHK92xfj5zKL",
        "public_key": "0290d6d88c8cd59b93d03bacc2ba85294c611f09f81135e19c342c00e74b667734",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1GmPCSWaebhJyxzfmwx1ba4xKzYPHCmMeu": {
        "privateKey": 70025129966660844615568173984891235870560178139308698142672555426639757977904,
        "public_addr": "1GmPCSWaebhJyxzfmwx1ba4xKzYPHCmMeu",
        "public_key": "03a6192bb0ec3e25c1622d38a7a8ed528e76a8c53718b93f092d238505dc08aa50",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1KQvBPgRLnJ6erTBQzQGZMjyvyRsL6fZDd": {
        "privateKey": 30647666996542319692169707505318583327680883980510798311790933601996184878018,
        "public_addr": "1KQvBPgRLnJ6erTBQzQGZMjyvyRsL6fZDd",
        "public_key": "0272e6ff1e0afb934d324969b3b0efae7780d0e244d484e4523cdb50288d15fb5b",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Dirqr6dEvYXiTf8dgpmo4fZhuhNFfFf28": {
        "privateKey": 27487023746680171012493230729352222717901385868117999119012092870266424720693,
        "public_addr": "1Dirqr6dEvYXiTf8dgpmo4fZhuhNFfFf28",
        "public_key": "0278c4b0ce8e1a9a70ae6b366a5535dc1abf6ffe5d30e3d756e90be52d85aedbaf",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "12zDWfi3tMqmdirJomzyYcTyBYfcC3XnLb": {
        "privateKey": 84608792458574459420447811584643764323614527379941948933200784050166171751005,
        "public_addr": "12zDWfi3tMqmdirJomzyYcTyBYfcC3XnLb",
        "public_key": "02eadaa48228a750c4863696ee1c93385b2878f43914e0cda38ffaec4fec92de96",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1DM3gZYDfTGr6dGPTLL1q1QYmYuHZ3W9U8": {
        "privateKey": 52750028920921105356946752412472840505898046754452336782142772312028601240279,
        "public_addr": "1DM3gZYDfTGr6dGPTLL1q1QYmYuHZ3W9U8",
        "public_key": "0359a1d7dc6885e4593d2af1785748f9bb3861215b378254b96201cf31faa6a3c5",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1HdpMavQGPbHtKKLTfa1JcYDTkeTQVrMqa": {
        "privateKey": 75114637318099113643314876194806218388682712243032669585679287198499862529291,
        "public_addr": "1HdpMavQGPbHtKKLTfa1JcYDTkeTQVrMqa",
        "public_key": "03c4fb95de6cff3d5cd4f63b712675899c3e08a1d9a3a38aa94af1a9e5ed0b91d9",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "14AS6da7nF4Wek2vWh7xskhXW1DSmmFQvk": {
        "privateKey": 83075003904492870616564287157419331918411837290727757160831247651918838783216,
        "public_addr": "14AS6da7nF4Wek2vWh7xskhXW1DSmmFQvk",
        "public_key": "029cf6ca7d000a634e84f079ee98c9a796e7fb8ce79ac8f008da90b4cb4873d7a6",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "14QjMVCDsg1Bn4dcU4Gq9BHv5qB97eQLmV": {
        "privateKey": 95776525205507721408835820400324460580309803128673501745075402392680618427728,
        "public_addr": "14QjMVCDsg1Bn4dcU4Gq9BHv5qB97eQLmV",
        "public_key": "028124b5f12f6e28b65c035dbbc94ba32ca1ab22bc64adeac0866e9e41287b228a",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1PHjxKNhDqDtfe4qExNUVoYXYEWHLZvfTz": {
        "privateKey": 38129336736083387509800175842604221584068496533954429124622302010216295754147,
        "public_addr": "1PHjxKNhDqDtfe4qExNUVoYXYEWHLZvfTz",
        "public_key": "03020a82303dafc18daece8dcc87c4c569b90bd35f4c5f6aab1c2262223b4830ff",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1uS4TH4UvM1YX58VxyNfdo2fmVH3VYajQ": {
        "privateKey": 96016236502315231694929718353166772366363497987131911558496783163865613357744,
        "public_addr": "1uS4TH4UvM1YX58VxyNfdo2fmVH3VYajQ",
        "public_key": "02747a7fcaee8d317860101c6ffbe02e7fb4d37a82cdb816e2213bce56bc30f70e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "13Fv9siYjoU6URJCpRasxVNYgo58nRZ3tC": {
        "privateKey": 39350215188180019754487740550862475870178312949553689091435605096654291155209,
        "public_addr": "13Fv9siYjoU6URJCpRasxVNYgo58nRZ3tC",
        "public_key": "02a8feaed5e3b068253109dfaead0e02e3e618ae7c28efd4b2b5bd0f7f0d50a14e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "16RV8x2ZjwTJCmJgAXVsw1jGL349JjKkin": {
        "privateKey": 67844985402721950337061047682844639693061877754141504673996181654397715653300,
        "public_addr": "16RV8x2ZjwTJCmJgAXVsw1jGL349JjKkin",
        "public_key": "0241027126c7862c107bfb4c5cb0f1dd105ecfbdc71e557a8eeb9b522a343d586b",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "12ShcLxvtBG4sFGPPrZQkkG436nPLd3QEi": {
        "privateKey": 62391584689896937261789868488180952190331940268256250400312210944364021136377,
        "public_addr": "12ShcLxvtBG4sFGPPrZQkkG436nPLd3QEi",
        "public_key": "037b016bddfa4e58b17372ff9099054cd7498100573c61177f9e974cfd8b638b23",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "142s2WoE8hhuxNRjScu8YZSyyGABF7pB2G": {
        "privateKey": 37416855262809447317794420609534658266521596772241594357474301023295539433973,
        "public_addr": "142s2WoE8hhuxNRjScu8YZSyyGABF7pB2G",
        "public_key": "03528d7706868de2667f600d01829aced56f0f113078b0c8a6ee99bf742ae50df9",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Lm8z7Cno3Y5BcvV8c3tMaj7wYN3c78jQB": {
        "privateKey": 51521494652104260227583115084485509066181232095391624941057906921136597115253,
        "public_addr": "1Lm8z7Cno3Y5BcvV8c3tMaj7wYN3c78jQB",
        "public_key": "033209c534d27a4834366111d09bdf22f0f734d775a34e30d53c2a9a5919971deb",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1AYKwmXf2sJvMgKnAco64CsQXKALhRN4ja": {
        "privateKey": 18182876679875921371421690347220483209554314575724350740937582518156161873789,
        "public_addr": "1AYKwmXf2sJvMgKnAco64CsQXKALhRN4ja",
        "public_key": "02d6ac21611624b1aecd59b780b8f049b6b1b1897421dfd1c61dd828529b3d0668",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "16czd8MsLpZ2DHKGNTFTzKjhiYXoV9Wsde": {
        "privateKey": 3349832301516430007171183840527671517206657124215678310912137846695025585705,
        "public_addr": "16czd8MsLpZ2DHKGNTFTzKjhiYXoV9Wsde",
        "public_key": "02693b78b43233f6751a9f3d8de5859f6eaa8beab68c43ef9332dd5ec315d96647",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Jpdsk6SJYtTFCCMXDE4FJihRSjuobJnGX": {
        "privateKey": 32247847798105786375813964344800492288453646000808688062149268666101725650309,
        "public_addr": "1Jpdsk6SJYtTFCCMXDE4FJihRSjuobJnGX",
        "public_key": "0254e786e1e7b3d23fcf5a426d5935f20e1c5ffccb4333189ecc78767b642f2141",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1m1JJXprqturGMzNA3bVUUw5cYVV5NpoK": {
        "privateKey": 60522757935189738871867418590677981369063702780865360019730728242271272169783,
        "public_addr": "1m1JJXprqturGMzNA3bVUUw5cYVV5NpoK",
        "public_key": "0366e7e1052d7a122abb8a439f58e74d07cbd6a4b045bedbd10b517cf4093ee0fb",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1AooY9BquSaSU1fhk8Kc6S8vPBk43PjHPW": {
        "privateKey": 126180531579730962507251310185993990773190794030819621574196449318092242426,
        "public_addr": "1AooY9BquSaSU1fhk8Kc6S8vPBk43PjHPW",
        "public_key": "039c046eee19ef3ba9e8af3bfd4ff29f42799ab407a89aca8a7189ae3017b54223",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1AhbfTfU4JAtVa4pgKnqbUWDh2iqTq1jWk": {
        "privateKey": 75745138014427829013439328961368282196970025372638266838771468899031727688606,
        "public_addr": "1AhbfTfU4JAtVa4pgKnqbUWDh2iqTq1jWk",
        "public_key": "029fdbcde35b66666d5eb0af602bf680a52eafb9ea408053f9495cb20983b560e0",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1CVeAxBSLkxXvmnUXLjXEzARQPyZFhBWyv": {
        "privateKey": 78992435899571444438293112112201692014964174348495521278289656834517463600423,
        "public_addr": "1CVeAxBSLkxXvmnUXLjXEzARQPyZFhBWyv",
        "public_key": "028e6121257d2e1eba7c6a83a36eb3fd60517c7628cc4acd0221458e8db8b56d2e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "17jU6JEoryPjWywytXcqPHJM4JarpPM8K1": {
        "privateKey": 45903980866798266521375989197704732319610120887992304303407465197170302283516,
        "public_addr": "17jU6JEoryPjWywytXcqPHJM4JarpPM8K1",
        "public_key": "02ae9ea4f47b551cef584b348d356cbf93657c481baafed9ed2a210334f703e059",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1FZs1c6cB6PBdgqiCWbvBz4uqSMJozhTnU": {
        "privateKey": 72010191900062803677397401965732739184455778195731863044815994882248907854719,
        "public_addr": "1FZs1c6cB6PBdgqiCWbvBz4uqSMJozhTnU",
        "public_key": "0306c8201ca3513270c8cae24e12a25f168c951cabc5ad1896c284d8a7a105c1bb",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1Q5MDbvBcNYbFd5aahn8NfYdNdKfNGzNLW": {
        "privateKey": 15216486478469861300261619013601073420866839533379021437064608746090495270681,
        "public_addr": "1Q5MDbvBcNYbFd5aahn8NfYdNdKfNGzNLW",
        "public_key": "03b2cab24c33e6d2e6bf38ad56f0aabb2c7f1e50a3049580b6b34536f64860a9ad",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1LgtPTQ6i829b6TnLT6D4qgRPCErLgAoxd": {
        "privateKey": 50948547387739521831704597269577940055234122132754610937785857568933484293151,
        "public_addr": "1LgtPTQ6i829b6TnLT6D4qgRPCErLgAoxd",
        "public_key": "03222bb2c2c7ce2b3e7ace8629194aa346b6089fb8064b2add78b4054df58c9c3d",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1E4NC69CVGYN2fr1uuRa9KkMoySLU3W7wm": {
        "privateKey": 65452650410074333812828930854327038970729320073330981850653130034539675160322,
        "public_addr": "1E4NC69CVGYN2fr1uuRa9KkMoySLU3W7wm",
        "public_key": "02e8b3659812f75689975c893e54e92496557a507cded96480ed9128dfd27798b3",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1KCEjTp2yvWef4XdRZHUcjix2LFDwQSUzz": {
        "privateKey": 115178867284299542429489708101546690481966545036041330941615193641437063140060,
        "public_addr": "1KCEjTp2yvWef4XdRZHUcjix2LFDwQSUzz",
        "public_key": "034f8015f490872b82638d6cb8d89036a67814c39a0f3358884edf09b009236830",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1PXEgmo5dqQPVSsLqAmjnm5Nb5csX5FuRe": {
        "privateKey": 108335920119640723731036236173795131286392747430979499264104802301812259415795,
        "public_addr": "1PXEgmo5dqQPVSsLqAmjnm5Nb5csX5FuRe",
        "public_key": "030154e00e2c64bdd0a55142bd5e98da1637d58e1209b3f8883dab1124965ec91b",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "19dVuMHmk2J8E7UfwaSSwuiJRJ5EVFqt4M": {
        "privateKey": 114266932042257755197268041931273243614993808390743133535010866879336086948833,
        "public_addr": "19dVuMHmk2J8E7UfwaSSwuiJRJ5EVFqt4M",
        "public_key": "02488a57db2e05cb893a07f405d2b25d3fa2a4dbd112f4153913539db9f69a1c7b",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "12cPmUUoVGLY9QQjk5iFmhXJjhtTND8GGj": {
        "privateKey": 109916288351838912534957671997168244058219988890140342659393169585584617097459,
        "public_addr": "12cPmUUoVGLY9QQjk5iFmhXJjhtTND8GGj",
        "public_key": "0278fd72d0e68272e9ed03586db6d26532055dc70aee967a8974d98f7a0fad3ec6",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1KgTZJHSWG4ypnEikumod7NERcoW15Dej1": {
        "privateKey": 55680392668921477710760971134182198643907458908547265580117256274055351301352,
        "public_addr": "1KgTZJHSWG4ypnEikumod7NERcoW15Dej1",
        "public_key": "02ee86d46ec4047e8d681df6ef59c86fa9204df400a57bb86682f335a45a5303b0",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "15YnsggkuWVVaSA3iiYY3bD5DqcK98kRMp": {
        "privateKey": 48223644048472217670236031066249666429804919946790506301241960014379452924397,
        "public_addr": "15YnsggkuWVVaSA3iiYY3bD5DqcK98kRMp",
        "public_key": "0232eef1b6f24b9de3b2d41c8554ef9795189157d2b524a70b0f0e46c6ec66ac79",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1N4cUZ6nMpFhjrQqZYBsm7oVxstmL7jGZf": {
        "privateKey": 114567513216448438233953971124234464868384755261063422324007753396995787481989,
        "public_addr": "1N4cUZ6nMpFhjrQqZYBsm7oVxstmL7jGZf",
        "public_key": "0229cf095a7c0c99e5021a05e87a8c8b0218c3717ae14c76a61c35680b00af61a8",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1NZfcuEzD4votCi1pKqFjbRnaLQmig4uxb": {
        "privateKey": 5151610950752054117854771656577477314142704935587842846068987705990580027631,
        "public_addr": "1NZfcuEzD4votCi1pKqFjbRnaLQmig4uxb",
        "public_key": "02615f3278c97c1c0734114461aec4ef2531ee3e6a44ddcd43bc1ca3963a9d62a6",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "128pSHp3sV7hEDKxMEdryanDxi5LiJ9KF2": {
        "privateKey": 18977926359073663186640889607953870589030160535593979905122200451558893038413,
        "public_addr": "128pSHp3sV7hEDKxMEdryanDxi5LiJ9KF2",
        "public_key": "02d13447ed3dad2feec96a58394a411d519240ad2d316d6796dc64aa5fb3abfbf5",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1A6kGKPKNtkZVAbZSQA9R9EDAcofxzhhWP": {
        "privateKey": 54080535582051303067359599943483833433213624717966944855334665985285665322153,
        "public_addr": "1A6kGKPKNtkZVAbZSQA9R9EDAcofxzhhWP",
        "public_key": "035ef03c116e4909b33857b270353819eb363529ba6d575793395978770a2dcd13",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1FsnWFVUg3NitAMhYG2kvbnRqMdUDGqMin": {
        "privateKey": 31383898991044052196316270371535788086287627325529133013146730819615368076568,
        "public_addr": "1FsnWFVUg3NitAMhYG2kvbnRqMdUDGqMin",
        "public_key": "0322d621e38a491b95fddf23f8ff20d934a60b491f0f3f6f82a80913fca2bcef5d",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "15Ybj53oeQVnb6VhvEcmcsnV7QQxVgm4wB": {
        "privateKey": 76531600441098843203268042389431731192275302905652174596905502272057016810232,
        "public_addr": "15Ybj53oeQVnb6VhvEcmcsnV7QQxVgm4wB",
        "public_key": "03981d89ad8a4ab386a3765a79cff2cef17255a06205019a311897c1cc68c48540",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1AG9xZcnVziABP2DgdEYfcpMA5qMqua3cV": {
        "privateKey": 61289360396617948878034626721190117524040215355484198278590051856102699805040,
        "public_addr": "1AG9xZcnVziABP2DgdEYfcpMA5qMqua3cV",
        "public_key": "02899d32e125c7ac18f11e467cdbf041d386d704a162a5d1843d46bb9a70549acf",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1NVRVFDwWhKhSEdgqZQomeY9zNEHtv3oG8": {
        "privateKey": 110029019483529810152867601965735962645033869599232759731283424505585301061881,
        "public_addr": "1NVRVFDwWhKhSEdgqZQomeY9zNEHtv3oG8",
        "public_key": "037e71fb2dbd03ddff7097abe71bd866ee313b0626af64d2182edb57faaf831193",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1QBNKRYUvowB3JnJsmxB682PnDeEE1hR5E": {
        "privateKey": 111309355904809793147601742151089840117879804791971940847520901446898909998560,
        "public_addr": "1QBNKRYUvowB3JnJsmxB682PnDeEE1hR5E",
        "public_key": "03f1d71ce16d0a1424136d6b1e21662a4dcc300bc522b1e66c7497c28f2dc7e1e4",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1EvpNFW3rrKdWwpT21dvCPfbRsJGyHMQQq": {
        "privateKey": 28942758065276699228737104574449638356784853336573896702026364205710075319855,
        "public_addr": "1EvpNFW3rrKdWwpT21dvCPfbRsJGyHMQQq",
        "public_key": "02f1e27760a1d7f269d5d83a9ef1dfda8682d92a6adb28f69c2d64c57b610a78a8",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1NUZ1BMLTDLY3aUgpG95uCt8cDHqqKFHyv": {
        "privateKey": 102467479699939148325956840652897675730861198086882051328899736712471247650195,
        "public_addr": "1NUZ1BMLTDLY3aUgpG95uCt8cDHqqKFHyv",
        "public_key": "02ff56f3621a14025a1e06275bb67a2f366dc609804772b68b67b3d5ff3b04001e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1989YEnuBDpiYTAteH1ESLc2PVpd7jUYeg": {
        "privateKey": 25556348461687506866023820153827912125251983784259397652169562125112234682712,
        "public_addr": "1989YEnuBDpiYTAteH1ESLc2PVpd7jUYeg",
        "public_key": "02c528dbaea6718785270e1e6f1483ce21df5d5c43441cb66e95ec14206f8586ef",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1GtknnjEbAMjrj3Ts134YTKb1oBA3KbcyK": {
        "privateKey": 27467647855241492750824525183209548434032782203033943518149330882320327947844,
        "public_addr": "1GtknnjEbAMjrj3Ts134YTKb1oBA3KbcyK",
        "public_key": "0319a4c7404b4941809ce9e509686c5b5a44873b3599851ebb07b2f885d3382724",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1CXTF2Z4sudQUdtHVKVzpMUCChWBQhmBAx": {
        "privateKey": 108879670593620429268300300594077526579904260358689910451460245208535271957872,
        "public_addr": "1CXTF2Z4sudQUdtHVKVzpMUCChWBQhmBAx",
        "public_key": "02f360bedae3745c23136b20074e5e04fd754b730e1f75a1f0c70d851d0de62b64",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1HCh4pktLmYbCP49Px2iBZZPG6aN9ZBUPN": {
        "privateKey": 55813310387626354111635923116669867596735606293127234527236605800011519248279,
        "public_addr": "1HCh4pktLmYbCP49Px2iBZZPG6aN9ZBUPN",
        "public_key": "027641df91e7c32e0dcb8f0e67b854b78b3ca049ab52631b341756fe6a91e6ab85",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1M3oj95CqYxwEeWw3Unr2TDmji5KmhNQcz": {
        "privateKey": 81613977746320836741827442532213107753918595669861386640609695659516400205257,
        "public_addr": "1M3oj95CqYxwEeWw3Unr2TDmji5KmhNQcz",
        "public_key": "03d1068f36355ec30b2d66d12d3157f1352cfa38edfae08068ac0e91398abd1758",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1BgSpUTAaLFpbKrfL7E3BhEFyegDBHB5NF": {
        "privateKey": 61593290053740810152240114834453016983994849160913466667994091679036608930628,
        "public_addr": "1BgSpUTAaLFpbKrfL7E3BhEFyegDBHB5NF",
        "public_key": "03d9227559cf91b9bb73444d5866fb62a097988a674f6d4f6eb93a5ca9090ab0dd",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1DE5aRDjpFvNTQhrag2EdjdPpadErPuGXy": {
        "privateKey": 79454994865404569629981349221501936984240665452019470322900098258361058737043,
        "public_addr": "1DE5aRDjpFvNTQhrag2EdjdPpadErPuGXy",
        "public_key": "025fc2c7b7febabb12b3c15c0c54cacb6f6a90c794c9c4c22766567fb77dbd30ce",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1PNSembHU9NkLhdDysf3FFDEvZBuXr9BNP": {
        "privateKey": 68810873559952497507373045971372623506792123094251420939061188898984954939278,
        "public_addr": "1PNSembHU9NkLhdDysf3FFDEvZBuXr9BNP",
        "public_key": "02b62828525622d13c04ee1af236f4e05f60ced829b8f2ef2b49f37687fafe4c85",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "148Qq8G1ZnpaWpfFfFD9pkXrNfRYwLMYDx": {
        "privateKey": 12783745453340257996131638284266178761801794804101258356879734367417024271757,
        "public_addr": "148Qq8G1ZnpaWpfFfFD9pkXrNfRYwLMYDx",
        "public_key": "0350e279e00a95d78115a25f3df3323579e873e3bf8693246465b809bbb63db112",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1CmBRcFoykk3Pvpb9fWdjvB65PdPvN1urh": {
        "privateKey": 66694378060128461589684487047781551636522607028571637351339024015906524227295,
        "public_addr": "1CmBRcFoykk3Pvpb9fWdjvB65PdPvN1urh",
        "public_key": "02b034ded624ebf7f8cbb5ff62c1460f91d125d2e5d54c2fa2bcfcb13817f458a6",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1CbYitWAhBdZLjEuW3NCVEebx2Rtav1874": {
        "privateKey": 98683226905947995796974742909154062800880064368688521655418605982912467913497,
        "public_addr": "1CbYitWAhBdZLjEuW3NCVEebx2Rtav1874",
        "public_key": "0306ee57cb9e1f66ec1c600ceb22b21b9e2f871c31ba45c2ca9bd84adb2fe658a6",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "19tAnTXxg9xrpTTZd72NRbG2p3dwfLuiCN": {
        "privateKey": 12132019507534510934842746776485840496148888964300984371648892297245730485376,
        "public_addr": "19tAnTXxg9xrpTTZd72NRbG2p3dwfLuiCN",
        "public_key": "03a9091e1217ecb5bb63c9bfb982193eaf0db28e95ac0e7cfb586cd28151114167",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1NyFpLxrdYEyDfLf3jUxSwqte99rgZ32jx": {
        "privateKey": 44605344417620315375239037728049666235275362193211703867626833991371995666918,
        "public_addr": "1NyFpLxrdYEyDfLf3jUxSwqte99rgZ32jx",
        "public_key": "032e61d546a4efbb8eec5153ef443bd5e8b8be85769e831a83eb1e349c812b5440",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1CxkEH2p8WjG59jcpqHvQx8XfkPuSm7FZU": {
        "privateKey": 27233436301767299908992247319790424637120688415256387668732078009783168912772,
        "public_addr": "1CxkEH2p8WjG59jcpqHvQx8XfkPuSm7FZU",
        "public_key": "022835563ee3bbd5c8ab9045fd1d362131194262824f48d349d5c5b2e10bbe8dfa",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "18Dq8JtQX6kPZ7tBTrwJZMqD1YKu5egMtq": {
        "privateKey": 90668224979716393878467928308376756097369196014087516464917313708722006249605,
        "public_addr": "18Dq8JtQX6kPZ7tBTrwJZMqD1YKu5egMtq",
        "public_key": "0399d7c8a021de369ee6462b4d60cccec6a924bd7452bff1528634f208ab6618b6",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1NS9811Y3r69n8tQqMGGzSEhr15MWByCqj": {
        "privateKey": 68846190639479153883174741116337833033902878474864468956499395917390670648873,
        "public_addr": "1NS9811Y3r69n8tQqMGGzSEhr15MWByCqj",
        "public_key": "02887976f080dbbe8b241c4ad2b65011a7fcb11dc7d6f588710ac0842cd0d62a92",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "17DPttEBBo6vRQbTQTkmhaJRU2dmhvUMHD": {
        "privateKey": 78478790029165428669331552855767427500692017735479693008161824582793773333261,
        "public_addr": "17DPttEBBo6vRQbTQTkmhaJRU2dmhvUMHD",
        "public_key": "020eb9a09f5754977748ff14cc9cb0a002a9bc6014b22dcabe67e5d882db42bedd",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1DydoA6viQj4S3jR7sAMy23totqvey7P1b": {
        "privateKey": 98965817879534762687508212164850654673589481994009518594896965038423106663344,
        "public_addr": "1DydoA6viQj4S3jR7sAMy23totqvey7P1b",
        "public_key": "022fabea68de83807337e2eab7820bd656b3fe58879935b7640f9c750c30e1f63e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1HEEGizdypg3MT87LwL5aRNcAwgen6XFmb": {
        "privateKey": 52124996779629026700033138821773551968606160416338970112001731376492703216414,
        "public_addr": "1HEEGizdypg3MT87LwL5aRNcAwgen6XFmb",
        "public_key": "024ba0f8d9b323e9a7d79300ac9666146aecfa68a530f49dcdeb503487ed857f17",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "14rzHHwRdtTHb9NMVDv5yG2Wu1nQ1BKCYm": {
        "privateKey": 30560365273325911278339799948334213905627585811386557837269062424316501795801,
        "public_addr": "14rzHHwRdtTHb9NMVDv5yG2Wu1nQ1BKCYm",
        "public_key": "03eaa787e0a790bfe634e8e463bb6bb1ffc0f9eb6ed706c711d08b711b19d8b37e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "12WtbLimvSppYw3svBmPTsr8R8voQkANEE": {
        "privateKey": 8451433781844712988709623893338422575982709658191644061625050131312293394095,
        "public_addr": "12WtbLimvSppYw3svBmPTsr8R8voQkANEE",
        "public_key": "0312698cf400e148f2085ac4fce8c0324c25c7b938bc9cc7abcc78c5135e51813a",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1PU5QNLNzkGAiZJ1M6Xf9wT5TWVDED9gNZ": {
        "privateKey": 53285108127648301128397873051557044349853586555778258619165813803974743818957,
        "public_addr": "1PU5QNLNzkGAiZJ1M6Xf9wT5TWVDED9gNZ",
        "public_key": "022a8103ba8ffef9850e7c0dbc45294eb1c0ad6fc3ae74173f90fd167c0e619acb",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "18Tgxwyn28Nj8BDFwr7KVbuzqX7sxjZwgi": {
        "privateKey": 31827881279499309358619860106955046461699893400759751246153628410158754120005,
        "public_addr": "18Tgxwyn28Nj8BDFwr7KVbuzqX7sxjZwgi",
        "public_key": "03209818246165185367f86710ff6f62b6d8742597d373eb6875cdad094458302a",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1LKvvwUcPLK3iMNRpnpjd5hNbDpWNuXhNF": {
        "privateKey": 7730957643324132804722193141253160048613833616778416110948444429791898406184,
        "public_addr": "1LKvvwUcPLK3iMNRpnpjd5hNbDpWNuXhNF",
        "public_key": "038b1a8527536818124b04596bed64a5baf64e0a85c3b8f00f4304776d53a6e08c",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "148Lkh2CEmuumnpNyuZnndi2HKorpt2fcn": {
        "privateKey": 78975691647125724050802487209860264812511172626836157503094512658829321917625,
        "public_addr": "148Lkh2CEmuumnpNyuZnndi2HKorpt2fcn",
        "public_key": "0364b6cde5bb8710d084068f7f8ff698903e81f10ae1e9617c7265fc126523d006",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1MTGoSfzbahpZ9nDtpAru9njUqctNeJNVT": {
        "privateKey": 33217201699877487365817057453224701685857321981163811800462738677033611972714,
        "public_addr": "1MTGoSfzbahpZ9nDtpAru9njUqctNeJNVT",
        "public_key": "0359314bf7fe695be30b36a56693af4dbb87dc722475d014143b8e9422c7bba489",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "13bxw63Eb4r6pwjHSZBKEu58H9x3WNpqpp": {
        "privateKey": 10448355503906868130465459251305868294722282960049449219099178961211438217807,
        "public_addr": "13bxw63Eb4r6pwjHSZBKEu58H9x3WNpqpp",
        "public_key": "02a59e16bfabdd1224b63196dfb6b54e1e323b8dc9aa76ad2be2550cc1915fec04",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "151kYWNKrj4GhCSJWkJZh93ajosnkGEMSi": {
        "privateKey": 114542068017291126153338335000260637887018498227117312322952733208876094975159,
        "public_addr": "151kYWNKrj4GhCSJWkJZh93ajosnkGEMSi",
        "public_key": "03dd8647164d4b52cae93758c546c57b2c35432040905609aa8c8a9d97cde2bf8e",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1EyKLZpDzCN4f3QMeaXgvKSyjtkCrXwbiW": {
        "privateKey": 97765769563967475713959517769146932275639683365383831900471971268328391257539,
        "public_addr": "1EyKLZpDzCN4f3QMeaXgvKSyjtkCrXwbiW",
        "public_key": "03dc6dee03fd14c1401dfd3638a2cf78329752735947b3c30cf698224273c131e1",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "15S2zjua53YEPmR6AEbAmhb92FUuAo4tFA": {
        "privateKey": 29566077477464760911662434854052258502653187490579681234407230186362317582140,
        "public_addr": "15S2zjua53YEPmR6AEbAmhb92FUuAo4tFA",
        "public_key": "03cb1d39988baea5b98aebe62fe0124322bf6b0b12b0cc5fb09de0cdb7e1cb0650",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1FykhFhnJUHjeSe5TkqRHdscjCWzrBEgpJ": {
        "privateKey": 105199738949847569903706498964977104407079103343625056826870528911684006980712,
        "public_addr": "1FykhFhnJUHjeSe5TkqRHdscjCWzrBEgpJ",
        "public_key": "037dfb9543b628e1a552dd2f56bf13cb3235be3974f310ab8aecb2e991697bc20c",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "13DtRiJnJzXKbdWo1zgFnYC2RNbrTbFXrE": {
        "privateKey": 70786781555112386942277400581343219867482879317583245089838284170523425572375,
        "public_addr": "13DtRiJnJzXKbdWo1zgFnYC2RNbrTbFXrE",
        "public_key": "02f3d44851fd4d1bf655e77f464cc866f425913bb8c5f11c5f84243f6719e52f95",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "1KDXgczWVWTzXUGL65mfzrcSXx9mCpjQfi": {
        "privateKey": 113748829072654977158825447144160597772150959979340454392769131435997213633354,
        "public_addr": "1KDXgczWVWTzXUGL65mfzrcSXx9mCpjQfi",
        "public_key": "03bc6016f4008c27ba7352de20bb3d3157695e1d526302039c8f87dcadbdd2833c",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    },
    "13UR1JboV8W8zopgcNTUAHYYM7P8tkxqcg": {
        "privateKey": 32960787842284777554126751802915769971308792073944134269954246248646058281757,
        "public_addr": "13UR1JboV8W8zopgcNTUAHYYM7P8tkxqcg",
        "public_key": "029e0a76b2efb9fc9ec1d900c584250d0eb9385f8995926ae2732d8585c3ed9c9d",
        "staked": 10000000000,
        "unspent": 10000000000,
        "locked_until": 0,
        "staking_history": "[]"
    }


}


def find_node_dirs(root_dir):
    """
    Scan the network_data folder for subdirectories that are either
    node directories (starting with 'node_') or the validator node directory.
    """
    node_dirs = []
    network_dir = os.path.join(root_dir, "network_data")
    if not os.path.exists(network_dir):
        return node_dirs
    for item in os.listdir(network_dir):
        if item.startswith("node_") or item == "validator_node":
            full_path = os.path.join(network_dir, item)
            if os.path.isdir(full_path):
                node_dirs.append(full_path)
    return sorted(node_dirs)

