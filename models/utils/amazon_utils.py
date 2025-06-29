from sp_api.base import Marketplaces

def sp_marketplace_mapper(marketplace: str):
    """
    Maps the marketplace string to the corresponding sp_api marketplace object.

    Args:
        marketplace (str): The marketplace string (e.g., 'US', 'CA').

    Returns:
        Marketplaces: The corresponding sp_api marketplace object.
    """

    sp_api_marketplace_mapping = {
        "US": Marketplaces.US,
        "CA": Marketplaces.CA,
        "MX": Marketplaces.MX,
    }

    return sp_api_marketplace_mapping.get(marketplace)