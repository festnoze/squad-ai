using Studi.AI.Chatbot.Front.Models;

namespace Studi.AI.Chatbot.Front.Services;
public interface IConversationService : IDisposable
{
    bool IsExchangesLoaded { get; }

    event Action? ApiCommunicationErrorNotification;
    event Action? OnConversationChanged;
    
    void AddNewMessage(bool isSaved = false, bool isStreaming = true);
    Task AnswerUserQueryAsync(string userName = "default");
    void AddStreamToLastMessage(string? messageChunk);
    void EndsMessageStream();
    ConversationModel GetConversation();
    bool IsLastMessageEditable();
    bool IsWaitingForLLM();
    void MarkConversationAsLoaded();
    void SetCurrentUser(string userName);
    void SetDeviceInfo(DeviceInfoModel deviceInfo);
    void SetIP(string ip);
    Task CreateVectorDbAsync();
}