using System.Linq;
using System.Text.Json;
using PoAssistant.Front.Data;
using PoAssistant.Front.Helpers;
using PoAssistant.Front.Infrastructure;

namespace PoAssistant.Front.Services;

public class ThreadMetierCdPService : IDisposable
{
    private readonly IExchangesRepository _exchangesRepository;
    private ThreadModel? messages = null;
    public event Action? OnThreadChanged = null;
    private bool isWaitingForLLM = false;
    public const string endPmTag = "[FIN_PM_ASSIST]";
    private static string endExchangeProposalMessage = "Ajouter des points à aborder avec le Project Manager si vous le souhaitez. Sinon, cliquez sur le bouton : 'Terminer l'échange' pour passer à l'étape de rédaction de l'US";

    public ThreadMetierCdPService(IExchangesRepository exchangesRepository)
    {
        _exchangesRepository = exchangesRepository;
        InitializeThread();
    }

    private void InitializeThread()
    {
        if (messages is null || !messages.Any())
        {
            messages = new ThreadModel(MessageModel.BusinessExpertName, string.Empty, true);
            isWaitingForLLM = false;
        }
    }

    public string GetMetierBriefIfReady()
    {
        if (messages is null ||
            !messages.Any() || 
            !messages!.First().IsSavedMessage || 
            messages!.First().Content.Length < 1)
            return string.Empty;

        return messages!.First().Content;
    }

    public string GetLatestBusinessExpertAnswerIfValidated()
    {
        if (messages == null ||
            !messages.Any() ||
            messages.Last().IsSender ||
            !messages!.Last().IsSavedMessage ||
            messages!.Last().Content.Length < 1)
            return string.Empty;

        // Handle end exchange case
        var lastMessage = messages!.Last();
        if (lastMessage.IsEndMessage && lastMessage.IsSavedMessage)
            return "[ENDS_EXCHANGE]";

        return lastMessage.Content;
    }

    public ThreadModel GetPoMetierThread()
    {
        return messages!;
    }

    private string? username = null;
    public void SetCurrentUser(string userName)
    {
        this.username = userName;
    }

    public bool IsEditingLastMessage()
    {
        return messages.Last().IsLastThreadMessage && !messages.Last().IsSavedMessage;
    }

    public void AddNewMessage(MessageModel newMessage)
    {
        if (messages is null)
            messages = new ThreadModel();

        newMessage.IsSavedMessage = false;
        messages!.Add(newMessage);

        SaveThread();
        HandleWaitingStateAndEndExchange();
    }

    public void LoadThreadByName(string exchangeNameTruncated, bool truncatedExchangeName = false)
    {
        _isExchangesLoaded = false;
        messages = _exchangesRepository.LoadUserExchange(username!, exchangeNameTruncated, truncatedExchangeName);
        if (messages is null)
            throw new InvalidOperationException($"Cannot load the thread as the exchange is not found for user: {username}");

        HandleWaitingStateAndEndExchange();
        OnThreadChanged?.Invoke();
    }

    public void SaveThread()
    {
        if (username is null)
            throw new InvalidOperationException($"Cannot save the thread as the user is not set to service: {nameof(ThreadMetierCdPService)}");

        var newThread = _exchangesRepository.SaveUserExchange(username, messages!);
        if (newThread) _isExchangesLoaded = false;
    }

    public void UpdateLastMessage(MessageModel updatedLastMessage)
    {
        if (messages is null || !messages.Any())
            throw new InvalidOperationException("Cannot modify the last messages as the thread don't has any message yet");

        messages.RemoveLastMessage();

        isWaitingForLLM = false;
        updatedLastMessage.IsSavedMessage = false;
        updatedLastMessage.IsStreaming = false;

        messages.Add(updatedLastMessage);
        SaveThread();

        HandleWaitingStateAndEndExchange();
    }

    public void DisplayStreamMessage(string? messageChunk)
    {
        if (messageChunk != null)
        {
            // New line are specific to the stream to allow stream spliting words and avoid win/mac issue
            isWaitingForLLM = true;
            messages!.Last().Content += messageChunk.Replace(StreamHelper.NewLineForStream, StreamHelper.WindowsNewLine);
            OnThreadChanged?.Invoke();
        }
    }

    public void DeleteMetierPoThread()
    {
        _isExchangesLoaded = false;
        messages = new ThreadModel();
        InitializeThread();
        OnThreadChanged?.Invoke();
    }

    public void EndMetierMetierExchange()
    {
        messages!.Add(new MessageModel(MessageModel.ProjectManagerName, "Le PO a maintenant rédigé la User Story et ses 'use cases'.", 0, true));
        isWaitingForLLM = false;
        NotifyForUserStoryReady();
        OnThreadChanged?.Invoke();
    }

    private void HandleWaitingStateAndEndExchange()
    {
        if (messages != null && messages.Any())
        {
            // Change end message of PO & make it editable by user
            if (messages!.Last().IsSender)
            {
                if (messages!.Last().Content.Contains(endPmTag) /*|| !messages!.Last().Content.Contains("?")*/)
                {
                    messages!.Last().ChangeContent(messages!.Last().Content.Replace(endPmTag, string.Empty)); //"Merci. Nous avons fini, j'ai tous les éléments dont j'ai besoin. Avez-vous d'autres points à aborder ?");
                    messages.Add(new MessageModel(MessageModel.BusinessExpertName, endExchangeProposalMessage, 0, false, true));
                    isWaitingForLLM = false;
                }
                else
                    isWaitingForLLM = true;
            }
            else if (!messages!.Last().IsSender)
                isWaitingForLLM = false;
        }
        else
            isWaitingForLLM = false;

        RefreshLastMessageInThread();
        OnThreadChanged?.Invoke();
    }

    private void RefreshLastMessageInThread()
    {
        if (messages != null && messages.Any())
        {
            messages!.RemoveLastThreadMessageFlags();

            if (!messages!.Last().IsSender)
                messages?.Last().SetAsLastThreadMessage();
        }
    }

    public bool IsWaitingForLLM()
    {
        return isWaitingForLLM;
    }

    public void EditingLastMessage()
    {
        if (messages != null && messages.Last().IsEndMessage)
            messages!.Last().ChangeContent(string.Empty);
    }

    public void ValidateMetierAnswer(string modifiedMessageContent)
    {
        if (!messages?.Any() ?? true)
            return;
        
        var lastMessage = messages!.Last();
        if (!string.IsNullOrWhiteSpace(modifiedMessageContent))
            lastMessage.Content = modifiedMessageContent;

        if (lastMessage.IsEndMessage && lastMessage.Content != endExchangeProposalMessage)
            lastMessage.IsEndMessage = false;

        lastMessage.IsSavedMessage = true;
        SaveThread();
    }

    public event Action? UserStoryReadyNotification;

    protected virtual void NotifyForUserStoryReady()
    {
        UserStoryReadyNotification?.Invoke();
    }

    public void DoEndBusinessPoExchange()
    {
        messages.Last().IsEndMessage = true;
        messages.Last().IsSavedMessage = true;
    }

    public void Dispose()
    {
    }

    public void InitStreamMessage()
    {
        if (messages is null)
            messages = new ThreadModel();

        var role = "Métier";
        if (messages?.Any() ?? false)
            role =  messages.Last().IsSender ? MessageModel.BusinessExpertName : MessageModel.ProjectManagerName;
        var newMessage = new MessageModel(role, string.Empty, -1, false);
        newMessage.IsStreaming = true;

        messages!.Add(newMessage);

        isWaitingForLLM = true;
        RefreshLastMessageInThread();
    }

    public void EndsStreamMessage()
    {
        messages!.Last().IsStreaming = false;
    }

    private bool _isExchangesLoaded = false;
    public bool IsExchangesLoaded()
    {
        return _isExchangesLoaded;
    }

    public void ExchangesIsLoaded()
    {
        _isExchangesLoaded = true;
    }
}
