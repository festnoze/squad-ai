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

[ScopedService(typeof(IMessageService))]
public class MessageService : IMessageService
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IMessageAttachmentService _messageAttachmentService;
    private readonly IConversationRepository _conversationRepository;
    private readonly IMessageRepository _messageRepository;
    private readonly IMessageAttachmentRepository _messageAttachmentRepository;
    private readonly IUserRepository _userRepository;
    private readonly ICorrespondantRepository _correspondantRepo/// <summary>
/// The method is a constructor for the 'MessageService' class, setting up dependencies and repositories for the class to function properly.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
sitory;

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
    /// description
    /// </summary>
    /// <param name="conversationId"></param>
    /// <param name="userId"></param>
    /// <returns><//// <summary>
/// This method allows retrieving the last message date for a conversation, excluding a specific user, by using the conversation ID and user ID as parameters.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <returns>DateTime?</returns>
returns>
    public async Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId)
    {
        return await _messageRepository.GetLastMessageDateByConversationIdExceptUserIdAsync(conversationId, userId);
    }

    /// <inheritdoc/>
    [Obsolete("This method is deprecated, use CountMessagesAsync ins/// <summary>
/// The 'CountMessagesAsync' method retrieves the count of messages using specific filters and sorting criteria.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolsIds">A collection of school IDs.</param>
/// <param name="listingSelector">An untyped listing selector.</param>
/// <returns>int</returns>
tead.")]
    public async Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector)
    {
        return await _messageRepository.CountMessagesWithFilterAndSort(userId, schoolsIds, listingSelector)/// <summary>
/// This method retrieves the count of filtered messages by conversation ID in an asynchronous manner.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolsIds">A collection of school IDs.</param>
/// <param name="listingSelector">An untyped listing selector.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="listingSelector">An optional listing selector used to filter the messages. Defaults to null if not provided.</param>
/// <returns>int</returns>
;
    }

    public async Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null)
    {
        return await _messageRepository.CountFilteredMessagesByConversationIdAsync(conversationId, listingSelector)/// <summary>
/// The method retrieves and formats the count of unread messages for a specific user and school.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolsIds">A collection of school IDs.</param>
/// <param name="listingSelector">An untyped listing selector.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="listingSelector">An optional listing selector used to filter the messages. Defaults to null if not provided.</param>
/// <param name="userId">The ID of the user for whom the unread message count is retrieved.</param>
/// <param name="schoolId">The ID of the school for which the unread message count is retrieved.</param>
/// <returns>IUnreadMessageCountAto</returns>
;
    }

    public async Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId)
    {
        var unreadMessageCountByConversation = await _messageRepository.GetUnreadMessagesByUserIdAndSchoolIdAsync(userId, schoolId);

        return unreadMessageCountByConversation.ToAto()/// <summary>
/// This method retrieves paginated messages by conversation ID asynchronously, checking if the conversation and user IDs exist and if the user ID is included in the list of correspondents.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolsIds">A collection of school IDs.</param>
/// <param name="listingSelector">An untyped listing selector.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="listingSelector">An optional listing selector used to filter the messages. Defaults to null if not provided.</param>
/// <param name="userId">The ID of the user for whom the unread message count is retrieved.</param>
/// <param name="schoolId">The ID of the school for which the unread message count is retrieved.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolIds">A list of school IDs.</param>
/// <param name="pageNumber">The page number for pagination.</param>
/// <param name="pageSize">The number of items per page for pagination.</param>
/// <returns>PaginedData<IMessageRAto></returns>
;
    }

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

        return paginedData/// <summary>
/// This method adds a message asynchronously and registers repositories for message-related entities.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolsIds">A collection of school IDs.</param>
/// <param name="listingSelector">An untyped listing selector.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="listingSelector">An optional listing selector used to filter the messages. Defaults to null if not provided.</param>
/// <param name="userId">The ID of the user for whom the unread message count is retrieved.</param>
/// <param name="schoolId">The ID of the school for which the unread message count is retrieved.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolIds">A list of school IDs.</param>
/// <param name="pageNumber">The page number for pagination.</param>
/// <param name="pageSize">The number of items per page for pagination.</param>
/// <param name="messageWAto">The message to be added. It should implement the IMessageWAto interface.</param>
/// <param name="enableNotification">Optional. Specifies whether to enable notifications for the added message. Default value is true.</param>
/// <returns>IMessageRAto</returns>
;
    }

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

        return message/// <summary>
/// This method retrieves a message and its associated information asynchronously, including the current user, sender, and any attachments. It also performs a specific action if there is an audio file attached to the message.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolsIds">A collection of school IDs.</param>
/// <param name="listingSelector">An untyped listing selector.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="listingSelector">An optional listing selector used to filter the messages. Defaults to null if not provided.</param>
/// <param name="userId">The ID of the user for whom the unread message count is retrieved.</param>
/// <param name="schoolId">The ID of the school for which the unread message count is retrieved.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolIds">A list of school IDs.</param>
/// <param name="pageNumber">The page number for pagination.</param>
/// <param name="pageSize">The number of items per page for pagination.</param>
/// <param name="messageWAto">The message to be added. It should implement the IMessageWAto interface.</param>
/// <param name="enableNotification">Optional. Specifies whether to enable notifications for the added message. Default value is true.</param>
/// <param name="messageId">The ID of the message to retrieve.</param>
/// <param name="currentUserId">The ID of the current user.</param>
/// <returns>IMessageRAto</returns>
;
    }

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

    /// <inhe/// <summary>
/// This method updates the 'IsArchived' status for a specific user and conversations by retrieving the conversations based on their IDs and the user ID, and checking if the user belongs to each conversation.
/// </summary>
/// <param name="messageAttachmentService">An instance of the 'IMessageAttachmentService' interface, used for handling message attachments.</param>
/// <param name="unitOfWork">An instance of the 'IUnitOfWork' interface, used for managing unit of work operations.</param>
/// <param name="conversationRepository">An instance of the 'IConversationRepository' interface, used for accessing conversation data.</param>
/// <param name="messageRepository">An instance of the 'IMessageRepository' interface, used for accessing message data.</param>
/// <param name="messageAttachmentRepository">An instance of the 'IMessageAttachmentRepository' interface, used for accessing message attachment data.</param>
/// <param name="userRepository">An instance of the 'IUserRepository' interface, used for accessing user data.</param>
/// <param name="correspondantRepository">An instance of the 'ICorrespondantRepository' interface, used for accessing correspondant data.</param>
/// <param name="conversationId">The ID of the conversation for which to retrieve the last message date.</param>
/// <param name="userId">The ID of the user to exclude when retrieving the last message date.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolsIds">A collection of school IDs.</param>
/// <param name="listingSelector">An untyped listing selector.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="listingSelector">An optional listing selector used to filter the messages. Defaults to null if not provided.</param>
/// <param name="userId">The ID of the user for whom the unread message count is retrieved.</param>
/// <param name="schoolId">The ID of the school for which the unread message count is retrieved.</param>
/// <param name="conversationId">The ID of the conversation.</param>
/// <param name="userId">The ID of the user.</param>
/// <param name="schoolIds">A list of school IDs.</param>
/// <param name="pageNumber">The page number for pagination.</param>
/// <param name="pageSize">The number of items per page for pagination.</param>
/// <param name="messageWAto">The message to be added. It should implement the IMessageWAto interface.</param>
/// <param name="enableNotification">Optional. Specifies whether to enable notifications for the added message. Default value is true.</param>
/// <param name="messageId">The ID of the message to retrieve.</param>
/// <param name="currentUserId">The ID of the current user.</param>
/// <param name="conversationIds">An array of integers representing the IDs of the conversations to update.</param>
/// <param name="archived">A boolean value indicating whether the conversations should be archived or not.</param>
/// <param name="userId">An integer representing the ID of the user for whom the conversations should be updated.</param>
/// <returns>Task</returns>
ritdoc/>
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