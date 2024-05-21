using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Studi.Api.Lms.Messenger.Application.Services.ConversationService;
using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.MessageService;
using Studi.Api.Lms.Messenger.Controllers.Conversation.Mapping;
using Studi.Api.Lms.Messenger.Controllers.Message.Mapping;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Conversation.RequestModels;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Conversation.ResponseModels;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Message.RequestModels;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Message.ResponseModels;
using Studi.Api.Lms.Messenger.Localization.Error.GeneratedClasses;
using Studi.Api.Lms.Messenger.Utils.Attributes;
using Swashbuckle.AspNetCore.Annotations;
using System.Net;
using Studi.Api.Lms.Messenger.Shared.ConversationListing;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Security.Authentication;
using Studi.Api.Core.ListingSelector;
using Studi.Api.Core.ListingSelector.Untyped;
using Studi.Api.Core.ListingSelector.Filtering.AvailableFilters;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation;

/// <summary>
/// Controller for managing conversations and related operations.
/// </summary>
[ApiController]
[Route("v{version:apiVersion}/conversations")]
[Authorize]
public class ConversationController : ControllerBase
{
    private readonly IConversationService _conversationService;
    private readonly IMessageService _messageService;
    private readonly IAvailableFilters<IConversationListing> _availableFiltersForConversation;

    /// <summary>
    /// Initializes a new instance of the <see cref="ConversationController"/> class.
    /// </summary>
    /// <param name="conversationService">The conversation service.</param>
    /// <param name="messageService">The message service.</param>
    /// <param name="availableFiltersForConversation">The available filters for conversations.</param>
    public ConversationController(IConversationService conversationService, IMessageService messageService, IAvailableFilters<IConversationListing> availableFiltersForConversation)
    {
        _conversationService = conversationService;
        _messageService = messageService;
        _availableFiltersForConversation = availableFiltersForConversation;
    }

    /// <summary>
    /// Creates a new conversation.
    /// </summary>
    /// <param name="conversationBM">The conversation request model.</param>
    /// <param name="userId">The user ID.</param>
    /// <param name="schoolIds">The school IDs.</param>
    /// <param name="enableNotification">Indicates whether to enable notification.</param>
    /// <returns>The response model of the created conversation.</returns>
    [HttpPost]
    [HttpCode(HttpStatusCode.Created)]
    [SwaggerOperation("CreateConversation")]
    [SwaggerResponse((int)HttpStatusCode.Created, Type = typeof(ConversationResponseModel))]
    [ApiVersion("1")]
    public async Task<ConversationResponseModel> CreateConversationAsync([FromBody] ConversationRequestModel conversationBM, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds, [FromQuery(Name = "enable-notification")] bool enableNotification = true)
    {
        var conversationAtoParam = Mapping.MappingAtoParam.CreateConversationAtoParam(conversationBM);

        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        var conversation = await _conversationService.CreateConversationAsync(conversationAtoParam, isRequestFromIntranet, enableNotification: enableNotification);

        return conversation.ToResponseModel(userId);
    }

    /// <summary>
    /// Creates a list of conversations.
    /// </summary>
    /// <param name="conversationBMs">The conversation request models.</param>
    /// <returns>The list of response models indicating if each conversation was created or not.</returns>
    [HttpPost]
    [HttpCode(HttpStatusCode.Created)]
    [Route("range")]
    [SwaggerOperation("CreateConversationsList")]
    [SwaggerResponse((int)HttpStatusCode.Created, Type = typeof(IEnumerable<ConversationCreatedOrNotResponseModel>))]
    [ApiVersion("1")]
    public async Task<IEnumerable<ConversationCreatedOrNotResponseModel>> CreateConversationsListAsync([FromBody] IEnumerable<ConversationRequestModel> conversationBMs)
    {
        var conversationAtoParams = conversationBMs.Select(c => Mapping.MappingAtoParam.CreateConversationAtoParam(c));

        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        var conversationCreatedOrNotAtos = await _conversationService.CreateRangeConversationAsync(conversationAtoParams, isRequestFromIntranet);
        var conversationCreatedOrNotVMs = conversationCreatedOrNotAtos.Select(c => Mapping.MappingResponseModel.CreateConversationCreatedOrNotResponseModel(c));

        return conversationCreatedOrNotVMs;
    }

    /// <summary>
    /// Count conversations based on provided criteria.
    /// </summary>
    /// <param name="listingSelector">The listing selector for filtering and pagination.</param>
    /// <param name="userId">The user ID.</param>
    /// <param name="schoolIds">The school IDs.</param>
    /// <returns>number of Conversations</returns>
    [HttpPost]
    [Route("count")]
    [SwaggerOperation("CountConversations")]
    [SwaggerResponse((int)HttpStatusCode.Created, Type = typeof(int))]
    [ApiVersion("1")]
    public async Task<int> CountConversationsAsync([FromBody] IListingSelector<IConversationListing> listingSelector, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-ids")] List<int> schoolIds)
    {
        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        var untypedListingSelector = listingSelector.ConvertToUntypedListingSelector();

        var countConversation = await _conversationService.GetConversationCountByUserIdAsync(userId, schoolIds, untypedListingSelector, isRequestFromIntranet);

        return countConversation;
    }

    /// <summary>
    /// Searches for paginated conversations based on provided criteria.
    /// </summary>
    /// <param name="listingSelector">The listing selector for filtering and pagination.</param>
    /// <param name="userId">The user ID.</param>
    /// <param name="schoolIds">The school IDs.</param>
    /// <returns>The paginated data of conversation response models.</returns>
    [HttpPost]
    [Route("get")]
    [SwaggerOperation("SearchPaginatedConversations")]
    [SwaggerResponse((int)HttpStatusCode.Created, Type = typeof(PaginedData<ConversationResponseModel>))]
    [ApiVersion("1")]
    public async Task<PaginedData<ConversationResponseModel>> SearchPaginatedConversationsAsync([FromBody] IListingSelector<IConversationListing> listingSelector, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
    {
        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        var untypedListingSelector = listingSelector.ConvertToUntypedListingSelector();

        var searchAndCountConversationRAto = await _conversationService.GetFilteredConversationsAndCountByUserIdAsync(userId, schoolIds, untypedListingSelector, isRequestFromIntranet);

        var paginedData = new PaginedData<ConversationResponseModel>
        {
            Data = searchAndCountConversationRAto.ConversationsListRAto.Select(q => q.ToResponseModel(userId)),
            PageNumber = listingSelector?.Pagination?.PageNumber ?? 0,
            PageSize = listingSelector?.Pagination?.PageSize ?? 0,
            Total = searchAndCountConversationRAto.ConversationCount,
        };

        return paginedData;
    }

    /// <summary>
    /// Retrieves general information about a conversation based on its identifier.
    /// </summary>
    /// <param name="conversationId">The identifier of the conversation.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolId">The school identifier, if applicable.</param>
    /// <returns>The general information about the specified conversation.</returns>
    [HttpGet]
    [Route("{conversationId:int}")]
    [SwaggerOperation("GetConversationGeneralInfos")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(ConversationResponseModel))]
    [ApiVersion("1")]
    public async Task<ConversationResponseModel> GetConversationGeneralInfosAsync(int conversationId, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] int? schoolId)
    {
        var schoolIds = schoolId != null ? new List<int> { (int)schoolId } : new List<int>();

        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        var conversationAto = await _conversationService.GetConversationByIdWithChecksAsync(conversationId, userId, schoolIds, isRequestFromIntranet)!;

        return conversationAto.ToResponseModel(userId);
    }

    /// <summary>
    /// Retrieves paginated messages associated with a specific conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the conversation.</param>
    /// <param name="listingSelector">The selector to specify pagination and other listing parameters.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolIds">List of school identifiers.</param>
    /// <returns>A paginated list of messages for the specified conversation.</returns>
    [HttpPost]
    [Route("{conversationId:int}/messages/get")]
    [SwaggerOperation("SearchPaginatedMessagesByConversation")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(MessageResponseModel))]
    [ApiVersion("1")]
    public async Task<PaginedData<MessageResponseModel>> GetPaginatedConversationMessagesAsync(int conversationId, [FromBody] IListingSelector<IConversationListing> listingSelector, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
    {
        var pageNumber = listingSelector.Pagination?.PageNumber ?? 1;
        var pageSize = listingSelector.Pagination?.PageSize ?? 25;

        Guard.Against.NegativeOrZero(pageNumber, ErrorCode.Api.Lms.Messenger.DataValidation.Query.Common.ListingSelector.Pagination.PageNumberIncorrect);
        Guard.Against.NegativeOrZero(pageSize, ErrorCode.Api.Lms.Messenger.DataValidation.Query.Common.ListingSelector.Pagination.PageSizeIncorrect);

        var paginedDataAto = await _messageService.GetPaginatedMessagesByConversationIdAsync(conversationId, userId, schoolIds, pageNumber, pageSize);

        var paginedData = new PaginedData<MessageResponseModel>
        {
            Data = paginedDataAto.Data.Select(m => m.ToResponseModel()),
            PageNumber = paginedDataAto.PageNumber,
            PageSize = paginedDataAto.PageSize,
            Total = paginedDataAto.Total,
        };

        return paginedData;
    }

    /// <summary>
    /// Archives or unarchives multiple conversations based on the provided details (relative to the user making the request).
    /// </summary>
    /// <param name="body">Details of the conversations to be archived or unarchived.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolIds">List of school identifiers.</param>
    [HttpPatch]
    [HttpCode(HttpStatusCode.NoContent)]
    [Route("is-archived")]
    [SwaggerResponse((int)HttpStatusCode.NoContent)]
    [SwaggerOperation("PatchIsArchivedMultipleConversations")]
    [ApiVersion("1")]
    public async Task PatchArchiveMultipleAsync([FromBody] PatchArchiveMultipleConversationRequestModel body, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
    {
        await _messageService.UpdateIsArchivedForUserIdByConversationsIdsAsync(body.Ids, body.IsArchived, userId);
    }

    /// <summary>
    /// Updates the status for multiple conversations based on the provided details (only for official).
    /// </summary>
    /// <param name="body">Details of the conversations whose status is to be updated.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolId">The school identifier.</param>
    [HttpPatch]
    [HttpCode(HttpStatusCode.NoContent)]
    [Route("status")]
    [SwaggerOperation("PatchStatusMultiple")]
    [SwaggerResponse((int)HttpStatusCode.NoContent)]
    [ApiVersion("1")]
    public async Task PatchStatusMultipleAsync([FromBody] PatchStatusMultipleConversationRequestModel body, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] int schoolId)
    {
        await _conversationService.ChangeMultipleConversationStatusAsync(body.Ids, (EConversationStatusRAto)body.ConversationStatus, userId, schoolId);
    }

    /// <summary>
    /// Updates the reading status for conversations based on the provided details (relative to the user making the request).
    /// </summary>
    /// <param name="markConversationAsReadOrUnread">Details to mark conversations as read or unread.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolIds">List of school identifiers.</param>
    [HttpPatch]
    [HttpCode(HttpStatusCode.NoContent)]
    [Route("reading-status")]
    [SwaggerResponse((int)HttpStatusCode.NoContent)]
    [ApiVersion("1")]
    public async Task ChangeReadedDateSenderAsync([FromBody] MarkConversationAsReadOrUnreadRequestModel markConversationAsReadOrUnread, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
    {
        await _conversationService.ChangeReadedDateAsync(markConversationAsReadOrUnread.Ids, markConversationAsReadOrUnread.MarkAsRead, userId, schoolIds.ToArray());
    }

    /// <summary>
    /// Adds recipients to a conversation based on the provided details.
    /// </summary>
    /// <param name="newRecipientsUsersIds">List of user identifiers to be added as recipients.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolIds">List of school identifiers.</param>
    /// <param name="id">The identifier of the conversation.</param>
    /// <returns>A list of correspondents that were added.</returns>
    [HttpPost]
    [Route("{id}/correspondants")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(ConversationCorrespondantResponseModel[]))]
    [SwaggerOperation("AddRecipients")]
    [ApiVersion("1")]
    public async Task<IEnumerable<ConversationCorrespondantResponseModel>> AddRecipientsAsync(
        [FromBody] IEnumerable<int> newRecipientsUsersIds,
        [FromQuery(Name = "user-id")] int userId,
        [FromQuery(Name = "school-id")] List<int> schoolIds,
        [FromRoute] int id)
    {
        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        var addedCorrespondentsAtos = await _conversationService.AddRecipientsAsync(id, userId, schoolIds, newRecipientsUsersIds, isRequestFromIntranet);
        var addedCorrespondents = addedCorrespondentsAtos?.Select(ato => ato.ToResponseModel(userId)).ToArray();

        return addedCorrespondents;
    }

    /// <summary>
    /// Removes recipients from a conversation based on the provided details.
    /// </summary>
    /// <param name="recipientsUsersIds">List of user identifiers to be removed as recipients.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolIds">List of school identifiers.</param>
    /// <param name="id">The identifier of the conversation.</param>
    [HttpDelete]
    [HttpCode(HttpStatusCode.NoContent)]
    [Route("{id}/correspondants")]
    [SwaggerResponse((int)HttpStatusCode.NoContent)]
    [SwaggerOperation("RemoveRecipients")]
    [ApiVersion("1")]
    public async Task RemoveRecipientsAsync(
        [FromBody] IEnumerable<int> recipientsUsersIds,
        [FromQuery(Name = "user-id")] int userId,
        [FromQuery(Name = "school-id")] List<int> schoolIds,
        [FromRoute] int id)
    {
        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        await _conversationService.RemoveRecipientsAsync(id, userId, schoolIds, recipientsUsersIds, isRequestFromIntranet);
    }

    /// <summary>
    /// Adds a new message to an existing conversation.
    /// </summary>
    /// <param name="conversationId">The identifier of the conversation.</param>
    /// <param name="newMessage">The content and details of the new message.</param>
    /// <param name="userId">The user identifier.</param>
    /// <param name="schoolId">The school identifier.</param>
    /// <param name="enableNotification">Flag to determine if notifications should be enabled for this message.</param>
    /// <returns>The created message details.</returns>
    [HttpPost]
    [Route("{conversationId:int}/messages")]
    [SwaggerOperation("AddMessageToExistingConversation")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(MessageResponseModel))]
    [ApiVersion("1")]
    public async Task<MessageResponseModel> AddNewMessageToConversationAsync(
        int conversationId,
        [FromBody] MessageRequestModel newMessage,
        [FromQuery(Name = "user-id")] int userId,
        [FromQuery(Name = "school-id")] int schoolId,
        [FromQuery(Name = "enable-notification")] bool enableNotification = true
    )
    {
        Guard.Against.Null(newMessage, ErrorCode.Api.Lms.Messenger.DataValidation.Command.Message.CreateMessage.AddToExistingConversation.UndefinedMessage, paramsValues: conversationId.ToString());
        var newMessageAddedToExistingConvAtoParam = Message.Mapping.MappingAtoParam.CreateMessageAtoParam(newMessage, userId, conversationId, schoolId);
        var responseOfMessageCreate = await _messageService.AddMessageAsync(newMessageAddedToExistingConvAtoParam!, enableNotification);
        return responseOfMessageCreate.ToResponseModel();
    }
}