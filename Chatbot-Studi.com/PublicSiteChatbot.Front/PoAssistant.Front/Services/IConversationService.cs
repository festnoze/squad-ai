using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;
public interface IConversationService : IDisposable
{
    bool IsExchangesLoaded { get; }

    event Action? ApiCommunicationErrorNotification;
    event Action? OnConversationChanged;

    void AddNewMessage(bool isSaved = false, bool isStreaming = true);
    void DeleteCurrentConversation();
    void DisplayStreamMessage(string? messageChunk);
    void EndsStreamMessage();
    ConversationModel GetConversation();
    bool IsLastMessageEditable();
    bool IsWaitingForLLM();
    void LoadConversationByName(string exchangeNameTruncated, bool truncatedExchangeName = false);
    void MarkConversationAsLoaded();
    void SaveConversation();
    void SetCurrentUser(string userName);
    Task<Guid> ApiCallGetNewConversationIdAsync(string? userName);
    Task ApiCallAnswerUserQueryAsync(ConversationModel conversation);
}