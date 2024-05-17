using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService.Ato;
using Studi.Api.Core.ListingSelector.Untyped;

namespace Studi.Api.Lms.Messenger.Application.Services.MessageService;

public interface IMessageService
{

    None    Task<DateTime?> GetLastMessageDateByConversationIdExceptUserIdAsync(int conversationId, int userId);

    None
    Task<int> CountMessagesAsync(int userId, IEnumerable<int> schoolsIds, IUntypedListingSelector listingSelector);

    None    Task<int> CountFilteredMessagesByConversationIdAsync(int conversationId, IUntypedListingSelector? listingSelector = null);

    None
    Task<IUnreadMessageCountAto> GetUnreadMessageCountByUserIdAndSchoolIdAsync(int userId, int schoolId);

    None
    Task<PaginedData<IMessageRAto>> GetPaginatedMessagesByConversationIdAsync(int conversationId, int userId, List<int> schoolIds, int pageNumber, int pageSize);

    None
    Task<IMessageRAto> AddMessageAsync(IMessageWAto messageWAto, bool enableNotification = true);

    None
    Task<IMessageRAto> GetMessageByIdAsync(int messageId, int currentUserId);

    None
    Task UpdateIsArchivedForUserIdByConversationsIdsAsync(int[] conversationIds, bool archived, int userId);
}