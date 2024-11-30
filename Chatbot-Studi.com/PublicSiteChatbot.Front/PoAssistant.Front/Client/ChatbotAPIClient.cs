using System.Text;
using System.Text.Json;
using PoAssistant.Front.Client;
using PoAssistant.Front.Helpers;

public class ChatbotAPIClient
{
    private readonly HttpClient _httpClient;
    private readonly string _baseUrl;

    public ChatbotAPIClient(string baseUrl)
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _httpClient = new HttpClient();
    }

    public async IAsyncEnumerable<string> GetQueryRagAnswerStreamingAsync(ConversationRequestModel conversationRequestModel)
    {
        string endpoint = $"{_baseUrl}/rag/query/stream";
        string jsonPayload = JsonSerializer.Serialize(conversationRequestModel);
        var request = new HttpRequestMessage(HttpMethod.Post, endpoint)
        {
            Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json")
        };

        using (HttpResponseMessage response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead))
        {
            response.EnsureSuccessStatusCode();

            using (var stream = await response.Content.ReadAsStreamAsync())
            using (var reader = new StreamReader(stream))
            {
                while (!reader.EndOfStream)
                {
                    var word = await reader.ReadWordAsync();
                    if (!string.IsNullOrEmpty(word))
                        yield return word;
                }
            }
        }
    }
}