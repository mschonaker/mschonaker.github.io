#!/usr/bin/env python
# /// script
# requires-python = ">=3.10"
# dependencies = ["laya"]
# ///
"""Show the Router's language routing decisions without loading any checkpoint."""
from laya import Router

questions = {"department": {"type": "choice", "instructions": "Which department?",
               "criteria": {"billing": "invoices, payments, refunds",
                            "technical": "bugs, outages, system errors",
                            "other": "everything else"}}}

router = Router()  # lazy: route() never downloads weights
for text in ["Please refund the duplicate charge on my invoice.",
             "मुझसे मार्च में दो बार शुल्क लिया गया, कृपया डुप्लिकेट राशि वापस करें।",
             "La aplicación se cierra cada vez que abro la configuración.",
             "Hello, world"]:
    r = router.route(text, questions)
    print(f"{text[:40]:42s} -> model={r.model:12s} reason: {r.reason}")
