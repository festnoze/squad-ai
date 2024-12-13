using Microsoft.VisualBasic;

namespace Studi.AI.Chatbot.Front.Models;

public class ConversationModel : List<MessageModel>
{
    public ConversationModel(Guid? id = null)
    {
        Id = id;
    }

    public Guid? Id { get; set; }
    public void RemoveLastConversationMessageFlags() => ForEach(msg => msg.SetAsNotLastConversationMessage());
    public void RemoveLastMessage() => RemoveAt(Count - 1);
    public bool IsLastMessageFromUser => this.Last().IsFromUser;
    public bool IsFirstUserMessage => this.Count(m => m.IsFromAI) == 1;

    public void AddMessage(string source, string content, int durationSeconds, bool isSavedMessage = true, bool isStreaming = false)
    {
        AddMessage(new MessageModel(source, content, durationSeconds, isSavedMessage, isStreaming));
    }

    public void AddMessage(MessageModel newMessage)
    {
        Add(newMessage);
        RefreshLastMessageInConversation();
    }

    private void RefreshLastMessageInConversation()
    {
        if (this.Any())
        {
            this!.RemoveLastConversationMessageFlags();

            if (!this!.Last().IsFromAI)
                this?.Last().SetAsLastConversationMessage();
        }
    }
}
