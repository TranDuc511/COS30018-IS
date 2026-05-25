def load_reviews_for_business(business_id: str) -> list[dict]:
    raise NotImplementedError("Implement Yelp review loading.")


def sample_reviews(reviews: list[dict], max_count: int = 100) -> list[dict]:
    raise NotImplementedError("Implement random review sampling.")

