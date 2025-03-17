import nltk
from textblob import TextBlob
from collections import Counter

# Download NLTK data (only needed once)
nltk.download('punkt')
nltk.download('averaged_perceptron_tagger')

def analyze_quote(quote):
    # Tokenize and count words
    words = nltk.word_tokenize(quote.lower())
    word_count = len(words)
    common_words = Counter(words).most_common(3)  # Top 3 words

    # Sentiment analysis
    blob = TextBlob(quote)
    sentiment = blob.sentiment.polarity  # -1 (negative) to 1 (positive)

    # Print results
    print(f"Quote: {quote}")
    print(f"Word Count: {word_count}")
    print(f"Top 3 Words: {common_words}")
    print(f"Sentiment: {sentiment} ({'positive' if sentiment > 0 else 'negative' if sentiment < 0 else 'neutral'})")

if __name__ == "__main__":
    quote = input("Enter a quote to analyze: ")
    analyze_quote(quote)
    input("Press Enter to exit...")