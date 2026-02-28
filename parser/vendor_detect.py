# Detect vendor from config text
"""
Vendor Detection Logic
Determines network OS from configuration text.
"""

def detect_vendor(config_text):
    text = config_text.lower()

    if "nx-os" in text or "feature " in text:
        return "Cisco Nexus (NX-OS)"

    if "arista" in text or "eos" in text:
        return "Arista EOS"

    if "dell emc networking" in text or "os10" in text:
        return "Dell OS10"

    if "ios" in text or "catalyst" in text:
        return "Cisco Catalyst (IOS/IOS-XE)"

    return "Unknown Vendor"