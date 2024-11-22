using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using PoAssistant.Front.Client;

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
                    var line = await reader.ReadLineAsync();
                    if (!string.IsNullOrWhiteSpace(line))
                        yield return line; // Return each chunk as part of the async enumeration
                }
            }
        }
    }
}