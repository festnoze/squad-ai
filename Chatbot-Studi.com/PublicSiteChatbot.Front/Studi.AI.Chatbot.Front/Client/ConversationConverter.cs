using Studi.AI.Chatbot.Front.Data;

namespace Studi.AI.Chatbot.Front.Client;

public static class ConversationConverter
{
    // Convert ConversationModel to UserQueryAskingRequestModel
    public static UserQueryAskingRequestModel ToUserQueryAskingRequestModel(this ConversationModel conversationModel)
    {
        return new UserQueryAskingRequestModel
        {
            ConversationId = conversationModel.Id ?? throw new InvalidOperationException("Conversation ID is not set"),
            UserQueryContent = conversationModel.Last().Content
        };
    }
    
    // Convert ConversationModel to ConversationRequestModel
    public static ConversationRequestModel ToRequestModel(this ConversationModel conversationModel)
    {
        return new ConversationRequestModel
        {
            Messages = conversationModel.Select(msg => new MessageRequestModel
            {
                Role = msg.Role,
                Content = msg.Content,
                DurationSeconds = msg.DurationSeconds
            }).ToList()
        };
    }

    // Convert ConversationRequestModel to ConversationModel
    public static ConversationModel ToConversationModel(this ConversationRequestModel requestModel)
    {
        var conversationModel = new ConversationModel();

        foreach (var msg in requestModel.Messages)
        {
            var messageModel = new MessageModel(
                source: msg.Role,
                content: msg.Content,
                durationSeconds: (int)msg.DurationSeconds // Assuming truncation to integer is acceptable
            );

            conversationModel.Add(messageModel);
        }

        return conversationModel;
    }
}

