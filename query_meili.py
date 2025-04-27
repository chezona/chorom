import meilisearch
import json

# Connect to Meilisearch
client = meilisearch.Client('http://localhost:7700') # No API key needed in development mode

# Define the index
index = client.index('products')

# Sample user query
user_query = "iphone price"

print(f"Searching for: '{user_query}'...")

# Perform the search
search_result = index.search(user_query)

# Print the results
print("\nSearch Results:")
print(json.dumps(search_result['hits'], indent=2)) # Pretty print the 'hits' part of the response

print(f"\nTotal hits: {search_result['estimatedTotalHits']}")
print(f"Processing time: {search_result['processingTimeMs']}ms") 