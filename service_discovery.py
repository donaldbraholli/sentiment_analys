import json


def discover_default_services(brand_name, market_name=None):
    """
    For now this is rule-based.
    Later we can replace this with AI-powered service discovery.
    """

    services = [
        {
            "service_name": "Mobile app",
            "category": "Digital service",
            "description": f"Customer sentiment about the {brand_name} mobile app, login, usability, bugs, balance checks, and account management.",
            "keywords": [
                "app",
                "mobile app",
                "my vodafone",
                "login",
                "account",
                "balance",
                "usage",
                "bug",
                "crash"
            ]
        },
        {
            "service_name": "Roaming",
            "category": "Mobile service",
            "description": "Sentiment about roaming charges, roaming activation, EU roaming, travel usage, and international connectivity.",
            "keywords": [
                "roaming",
                "abroad",
                "travel",
                "EU roaming",
                "international",
                "charges abroad"
            ]
        },
        {
            "service_name": "Mobile data",
            "category": "Mobile service",
            "description": "Sentiment about mobile internet, data allowance, speed, throttling, and data usage.",
            "keywords": [
                "data",
                "mobile data",
                "internet",
                "4G",
                "5G",
                "speed",
                "slow internet",
                "data usage"
            ]
        },
        {
            "service_name": "Network quality",
            "category": "Network",
            "description": "Sentiment about coverage, dropped calls, weak signal, outages, and network reliability.",
            "keywords": [
                "network",
                "coverage",
                "signal",
                "no service",
                "dropped call",
                "outage",
                "reception"
            ]
        },
        {
            "service_name": "5G",
            "category": "Network",
            "description": "Sentiment about 5G availability, speed, coverage, and device compatibility.",
            "keywords": [
                "5G",
                "5g coverage",
                "5g speed",
                "5g network"
            ]
        },
        {
            "service_name": "Broadband",
            "category": "Home service",
            "description": "Sentiment about home broadband, Wi-Fi, installation, router, speed, and outages.",
            "keywords": [
                "broadband",
                "wifi",
                "router",
                "home internet",
                "fiber",
                "fibre",
                "installation"
            ]
        },
        {
            "service_name": "Billing",
            "category": "Account service",
            "description": "Sentiment about bills, unexpected charges, payments, refunds, and account balance.",
            "keywords": [
                "bill",
                "billing",
                "charged",
                "payment",
                "refund",
                "invoice",
                "unexpected charge"
            ]
        },
        {
            "service_name": "Customer support",
            "category": "Support",
            "description": "Sentiment about call centres, chat support, complaint handling, wait times, and issue resolution.",
            "keywords": [
                "support",
                "customer service",
                "call centre",
                "agent",
                "complaint",
                "help",
                "waiting"
            ]
        },
        {
            "service_name": "Top up",
            "category": "Prepay",
            "description": "Sentiment about prepaid top ups, vouchers, balance, and failed payments.",
            "keywords": [
                "top up",
                "prepay",
                "credit",
                "voucher",
                "balance"
            ]
        },
        {
            "service_name": "SIM and eSIM",
            "category": "Mobile service",
            "description": "Sentiment about SIM cards, eSIM activation, replacement SIMs, number transfer, and setup.",
            "keywords": [
                "sim",
                "esim",
                "activation",
                "number transfer",
                "porting",
                "replacement sim"
            ]
        }
    ]

    return services


def services_to_db_format(services):
    formatted = []

    for service in services:
        formatted.append({
            "service_name": service["service_name"],
            "category": service["category"],
            "description": service["description"],
            "keywords": json.dumps(service["keywords"])
        })

    return formatted