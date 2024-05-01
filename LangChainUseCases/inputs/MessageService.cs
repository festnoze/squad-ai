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
    private readonly ICorrespondantRepository _correspondantRepository;

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
    /// <returns></returns>
    public async Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId)
    {
        return await _messageRepository.GetLastMessageDateByConversationIdExceptUserIdAsync(conversationId, userId);
    }

    /// <inheritdoc/>
    [Obsolete("This method is deprecated, use CountMessagesAsync instead.")
    public async Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector)
    {
        return await _messageRepository.CountMessagesWithFilterAndSort(userId, schoolsIds, listingSelector);
    }

    public async Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null)
    {
        return await _messageRepository.CountFilteredMessagesByConversationIdAsync(conversationId, listingSelector);
    }

    public async Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId)
    {
        var unreadMessageCountByConversation = await _messageRepository.GetUnreadMessagesByUserIdAndSchoolIdAsync(userId, schoolId);

        return unreadMessageCountByConversation.ToAto();
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

        return paginedData;
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

        return message;
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

    /// <inheritdoc/>
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