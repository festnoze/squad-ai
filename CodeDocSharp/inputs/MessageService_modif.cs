using Hangfire;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Infrastructure.Repository.UnitOfWork;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageAttachmentService;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Mapping;
using Studi.Api.Lms.Messenger.Application.Services.NotificationService;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.ConversationRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.CorrespondantRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageAttachmentRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageRepository;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageRepository.Ito;
using Studi.Api.Lms.Messenger.Infra.Data.Repositories.MessageRepository.Ito.Implementation;
using Studi.Api.Lms.Messenger.Infra.External.Data.Repositories.UserRepository;
using Studi.Api.Lms.Messenger.Localization.Error.GeneratedClasses;
using Studi.Api.Core.ListingSelector.Untyped;
using Studi.Api.Core.ListingSelector;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

using System.Collections.Generic;
using System.Threading.Tasks;
using System;

[ScopedService(typeof(IMessageService))]
public class MessageService : IMessageService
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IMessageAttachmentService _messageAttachmentService;
    private readonly IConversationRepository _conversationRepository;
    private readonly IMessageRepository _messageRepository;
    private readonly IMessageAttachmentRepository _messageAttachmentRepository;
    private readonly IUserRepository _userRepository;


    /// <summary>
    /// Count the number of messages for a specified user from defined schools with particular filtering and sorting criteria.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose archive status needs to be updated.</param>
    /// <param name="schoolsIds">A collection of school IDs to specify which schools' conversations should be considered.</param>
    /// <param name="listingSelector">An object used to filter and select the relevant conversations based on predefined criteria.</param>
    /// <returns>Returns the count of filtered messages for a specified user across defined schools.</returns>
    [Obsolete("This method is deprecated, use CountMessagesAsync instead.")]
    public async Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector)
    {
        return await _messageRepository.CountMessagesWithFilterAndSort(userId, schoolsIds, listingSelector);
    }


    /// <summary>
    /// Initialize dependencies for handling messages, attachments, conversations, users, and correspondents.
    /// </summary>
    /// <param name="messageAttachmentService">An instance of IMessageAttachmentService used to manage message attachments within the MessageService constructor.</param>
    /// <param name="unitOfWork">An instance of IUnitOfWork to handle transactions and ensure data consistency across repositories within the MessageService constructor.</param>
    /// <param name="conversationRepository">An instance of IConversationRepository used to interact with conversation data in the MessageService constructor.</param>
    /// <param name="messageRepository">An instance of IMessageRepository used to manage and retrieve messages in the MessageService constructor.</param>
    /// <param name="messageAttachmentRepository">An instance of IMessageAttachmentRepository used to handle message attachments data in the MessageService constructor.</param>
    /// <param name="userRepository">An instance of IUserRepository used to manage user data within the MessageService constructor.</param>
    /// <param name="correspondantRepository">An instance of ICorrespondantRepository used to manage correspondent data within the MessageService constructor.</param>
    public MessageService(
        IMessageAttachmentService messageAttachmentService,
        IUnitOfWork unitOfWork,
        IConversationRepository conversationRepository,
        IMessageRepository messageRepository,
        IMessageAttachmentRepository messageAttachmentRepository,
        IUserRepository userRepository,
        ICorrespondantRepository correspondantRepository
    )
    {
        _messageAttachmentService = messageAttachmentService;
        _unitOfWork = unitOfWork;
        _conversationRepository = conversationRepository;
        _messageRepository = messageRepository;
        _messageAttachmentRepository = messageAttachmentRepository;
        _userRepository = userRepository;
        _correspondantRepository = correspondantRepository;
    }


    /// <summary>
    /// Retrieve the date of the last message in a specific conversation, excluding messages from a specified user.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation. This parameter is used to specify which conversation's last message date we want to update.</param>
    /// <param name="userId">The unique identifier for the user. This parameter is used to exclude messages from this particular user during the update operation.</param>
    /// <returns>Returns the last message date in a conversation, excluding a specified user's messages.</returns>
    [Obsolete("This method is deprecated, use CountMessagesAsync instead.")]
    [Property("This method is deprecated, use CountMessagesAsync instead.")]
    public async Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId)
    {
        return await _messageRepository.GetLastMessageDateByConversationIdExceptUserIdAsync(conversationId, userId);
    }

    /// <summary>
    /// Count messages for a specific conversation based on given criteria.
    /// </summary>
    /// <param name="conversationId">The unique identifier of the conversation. This parameter is used to specify which conversation will be targeted for filtering messages.</param>
    /// <param name="listingSelector">An optional selector to filter and list conversations. If not provided, it defaults to null. This parameter helps in determining the set of conversations to consider for updating the archive status.</param>
    /// <returns>Returns the count of filtered messages for a specified conversation.</returns>
    public async Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null)
    {
        return await _messageRepository.CountFilteredMessagesByConversationIdAsync(conversationId, listingSelector);
    }
    
	[Obsolete("This method is deprecated, use CountMessagesAsync instead.")]
    [Obsolete("This method is soon deprecated, use CountMessagesAsync instead.")]

    /// <summary>
    /// Retrieve the count of unread messages for a specified user and school.
    /// </summary>
    /// <param name="userId">The ID of the user for whom unread messages are being counted. This parameter identifies the specific user in the system.</param>
    /// <param name="schoolId">The ID of the school associated with the user. This parameter is used to filter messages that belong to a particular school.</param>
    /// <returns>Returns the number of unread messages for a user at a specific school.</returns>
    public async Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId)
    {
        var unreadMessageCountByConversation = await _messageRepository.GetUnreadMessagesByUserIdAndSchoolIdAsync(userId, schoolId);

        return unreadMessageCountByConversation.ToAto();
    }

    private ICorrespondantRepository _correspondantRepository;

    /// <summary>
    /// Retrieve a paginated list of messages for a specified conversation after verifying the conversation exists and ensuring the requesting user is a participant in the conversation.
    /// </summary>
    /// <param name="conversationId">The unique identifier for the conversation. Used to filter messages to a specific conversation.</param>
    /// <param name="userId">The unique identifier for the user. Used to identify which user's archive status needs to be updated.</param>
    /// <param name="schoolIds">A list containing the unique identifiers of the schools. Used to filter conversations that belong to these specific schools.</param>
    /// <param name="pageNumber">The number of the page to be retrieved. Used for paginating the results of the messages.</param>
    /// <param name="pageSize">The number of messages per page. Used to limit the number of messages retrieved in one page.</param>
    /// <returns>Returns a paginated list of conversation messages.</returns>
    public async Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize)
    {
        var conversation = await _conversationRepository.GetConversationByIdAsync(conversationId);

        Guard.Against.Null(conversation, ErrorCode.Api.Lms.Messenger.DataValidation.Query.Conversation.NotFoundById, paramsValues: conversationId.ToString());

        var conversationUserIds = await _conversationRepository.GetCorrespondantsUserIdsByConversationIdAsync(conversationId);

        Guard.Against.False(conversationUserIds.Contains(userId), ErrorCode.Api.Lms.Messenger.DataValidation.Query.Conversation.UserNotInCorrespondants, paramsValues: new string[] { userId.ToString(), conversationId.ToString() });

        // Get total
        var total = await CountFilteredMessagesByConversationIdAsync(conversationId);

        var take = pageSize;
        var skip = (pageNumber - 1) * take;

        IEnumerable<IMessageRIto> messages = Enumerable.Empty<IMessageRIto>();

        if (total > 0)
        {
            messages = (await _messageRepository.GetPaginatedMessagesByConversationIdAsync(conversationId, skip, take));
        }

        var usersIds = messages.Select(m => m.SenderCorrespondant.UserId).Distinct().ToList();

        var users = await _userRepository.GetUsersByIdsAsync(usersIds);

        var flattenUploadedFileGuids = messages
            .SelectMany(m =>
            {
                var guids = new List<Guid>();

                guids.AddRange(m.AttachmentsUploadedFiles.Select(a => a.UploadedFileGuid));

                if (m.AudioMessageUploadedFile != null)
                {
                    guids.Add(m.AudioMessageUploadedFile.UploadedFileGuid);
                }

                return guids;
            }).Distinct();

        var flattenMessageAttachements = await _messageAttachmentService.GetMultipleMessageAttachmentbyGuidsAsync(flattenUploadedFileGuids);

        var currentUser = await _userRepository.GetUserByIdAsync(userId);
        Guard.Against.Null(currentUser, ErrorCode.Api.Lms.Messenger.DataValidation.Query.User.NotFoundById, paramsValues: userId.ToString());

        // pagined data
        var paginedData = new PaginedData<IMessageRAto>
        {
            Data = messages.Select(m => m.ToAto(users.Single(u => u.Id == m.SenderCorrespondant.UserId), currentUser, flattenMessageAttachements)),
            PageNumber = pageNumber,
            PageSize = pageSize,
            Total = total,
        };

        return paginedData;
    }


    /// <summary>
    /// Add a new message to the system for a specified user.
    /// </summary>
    /// <param name="messageWAto">The information structure that holds the details of the WhatsApp message to be added. This parameter encapsulates all necessary data for processing the message.</param>
    /// <param name="enableNotification">Flag to indicate whether notifications should be enabled or not. Default value is true, suggesting notifications will be sent unless explicitly set to false.</param>
    /// <returns>Returns a task representing the asynchronous message addition operation.</returns>
    public async Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true)
    {
        int messageCreatedId;
        var currentUser = await _userRepository.GetUserByIdAsync(messageWAto.UserId);

        await _unitOfWork.RegisterRepositoryAsync(_messageRepository);
        await _unitOfWork.RegisterRepositoryAsync(_messageAttachmentRepository);
        await _unitOfWork.RegisterRepositoryAsync(_correspondantRepository);

        try
        {
            var conversationCorrespondants = (await _conversationRepository.GetCorrespondantsByConversationIdAsync(messageWAto.ConversationId));

            Guard.Against.False(conversationCorrespondants.Any(corr => corr.UserId == messageWAto.UserId), ErrorCode.Api.Lms.Messenger.DataValidation.Query.Correspondant.MissingCorrespondantForMessageSender, paramsValues: messageWAto.UserId.ToString());

            var senderCorrespondantId = conversationCorrespondants.First(corr => corr.UserId == messageWAto.UserId).CorrespondantId;

            var messageWIto = MessageWIto.Create(messageWAto.ConversationId, senderCorrespondantId, messageWAto.MessageContent);

            var messageRIto = await _messageRepository.AddMessageAsync(messageWIto, currentUser.Email);

            await _messageAttachmentService.AddMessageAttachmentsAsync(messageRIto.Id, messageWAto.AttachmentsUploadedFilesGuids, messageWAto.AudioMessageGuid, currentUser.Email);

            await _correspondantRepository.UpdateIsArchivedForAllCorrespondantsByConversationsIdsAsync(new int[] { messageWAto.ConversationId }, false, currentUser.Email);

            messageCreatedId = messageRIto.Id;

            await _unitOfWork.CommitAsync();
        }
        catch (Exception)
        {
            await _unitOfWork.RollbackAsync();
            throw;
        }

        var guids = messageWAto.AttachmentsUploadedFilesGuids.ToList();
        if (messageWAto.AudioMessageGuid != null)
        {
            guids.Add((Guid)messageWAto.AudioMessageGuid);
        }

        var flattenMessageAttachements = await _messageAttachmentService.GetMultipleMessageAttachmentbyGuidsAsync(guids);

        var message = (await _messageRepository.GetMessageByIdAsync(messageCreatedId)).ToAto(currentUser, currentUser, flattenMessageAttachements);

        if (enableNotification)
        {
            BackgroundJob.Enqueue<INotificationService>(service => service.SendNewMessageWebsocketsEventAsync(message.Id));

            BackgroundJob.Enqueue<INotificationService>(service => service.SendNewMessageNotificationAsync(message.Id));
        }

        return message;
    }


    /// <summary>
    /// Get details of a specific message, including sender and recipient information, as well as any associated attachments.
    /// </summary>
    /// <param name="messageId">The unique identifier of the message to be updated.</param>
    /// <param name="currentUserId">The ID of the user currently performing the update operation.</param>
    /// <returns>Returns message details including sender, recipient, and attachments.</returns>
    public async Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId)
    {
        var messageRIto = await _messageRepository.GetMessageByIdAsync(messageId);

        var currentUser = await _userRepository.GetUserByIdAsync(currentUserId);

        var user = await _userRepository.GetUserByIdAsync(messageRIto.SenderCorrespondant.UserId);

        var guids = messageRIto.AttachmentsUploadedFiles.Select(a => a.UploadedFileGuid).ToList();
        if (messageRIto.AudioMessageUploadedFile != null)
        {
            guids.Add(messageRIto.AudioMessageUploadedFile.UploadedFileGuid);
        }

        var flattenMessageAttachements = await _messageAttachmentService.GetMultipleMessageAttachmentbyGuidsAsync(guids);

        return messageRIto.ToAto(user, currentUser, flattenMessageAttachements);
    }


    /// <summary>
    /// Update the archive status for a user across specified conversations by filtering relevant conversations and adjusting their status accordingly.
    /// </summary>
    /// <param name="conversationIds">A list of conversation IDs that need to be updated with the archive status.</param>
    /// <param name="archived">A boolean flag indicating whether the specified conversations should be marked as archived (true) or unarchived (false).</param>
    /// <param name="userId">The unique identifier of the user for whom the archive status needs to be updated.</param>
    public async Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId)
    {
        var conversations = await _conversationRepository.GetConversationsByConversationIdsAndUserIdAsync(conversationIds, userId);
                
        List<string> conversationsIdsWhereUserIdDontBelongs = new();

        foreach (var conversation in conversations)
        {
            var correspondants = await _conversationRepository.GetCorrespondantsByConversationIdAsync(conversation.Id);
            if (!correspondants.Any(cor => cor.UserId == userId))
                conversationsIdsWhereUserIdDontBelongs.Add(conversation.Id.ToString());
        }

        // Check if the user belongs to all the conversations he want to update
        Guard.Against.NotEmpty(
            conversationsIdsWhereUserIdDontBelongs, 
            ErrorCode.Api.Lms.Messenger.DataValidation.Command.Conversation.Archive.MissingRightOnEntity, 
            paramsValues: string.Join(", ", conversationsIdsWhereUserIdDontBelongs));
 
        // Check if the number of records persisted in the database correspond to the number of conversations to update
        Guard.Against.NotEqual(conversationIds.Count(), conversations.Count(), ErrorCode.Api.Lms.Messenger.DataValidation.Command.Conversation.Archive.WrongEntityCount);

        var currentUser = await _userRepository.GetUserByIdAsync(userId);

        await _correspondantRepository.UpdateIsArchivedForUserIdByConversationsIdsAsync(conversationIds, userId, archived, currentUser.Email);
    }
}