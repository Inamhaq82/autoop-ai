from autoops.llm.client import OpenAIClient


def main():
    client = OpenAIClient()
    result = client.generate("Hello world")
    print(result)


if __name__ == "__main__":
    main()
