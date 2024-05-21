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

[ApiController]
[Route("v{version:apiVersion}/conversations")]
[Authorize]
public class ConversationController : ControllerBase
{
    private readonly IConversationService _conversationService;
    private readonly IMessageService _messageService;
    private readonly IAvailableFilters<IConversationListing> _availableFiltersForConversation;


    /// <summary>
    /// Initialize a ConversationController with the necessary services and filters.
    /// </summary>
    /// <param name="conversationService">This parameter is of type IConversationService and represents the service responsible for managing conversations.</param>
    /// <param name="messageService">This parameter is of type IMessageService and represents the service responsible for managing messages within conversations.</param>
    /// <param name="availableFiltersForConversation">This parameter is of type IAvailableFilters<IConversationListing> and represents the available filters that can be applied to conversation listings.</param>
    public ConversationController(IConversationService conversationService, IMessageService messageService, IAvailableFilters<IConversationListing> availableFiltersForConversation)
    {
        _conversationService = conversationService;
        _messageService = messageService;
        _availableFiltersForConversation = availableFiltersForConversation;
    }


    /// <summary>
    /// Create a conversation with specified parameters and enable notifications if necessary.
    /// </summary>
    /// <param name="conversationBM">The ConversationRequestModel object containing the details of the conversation to be created.</param>
    /// <param name="userId">The integer representing the unique identifier of the user initiating the conversation.</param>
    /// <param name="schoolIds">The list of integers representing the unique identifiers of the schools associated with the conversation.</param>
    /// <param name="enableNotification">The boolean indicating whether notifications for the created conversation should be enabled. Defaults to true if not specified.</param>
    /// <returns>Returns a Task representing the asynchronous creation of a conversation.</returns>
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
    /// Create a list of conversations asynchronously based on specified parameters, returning the result as view models.
    /// </summary>
    /// <param name="conversationBMs">The IEnumerable of ConversationRequestModel instances representing conversation business models. These models will be used to create a list of conversations asynchronously.</param>
    /// <returns>Returns a Task<List<ConversationViewModel>> representing a list of conversations view models.</returns>
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
    /// Retrieve the count of conversations for a specified user, considering various conditions like user type and school IDs.
    /// </summary>
    /// <param name="listingSelector">IListingSelector<IConversationListing> listingSelector: The parameter represents a selector for conversation listings. It allows specifying the type of conversation listing to retrieve.</param>
    /// <param name="userId">int userId: The parameter holds the unique identifier of the user for whom the conversation count is being retrieved.</param>
    /// <param name="schoolIds">List<int> schoolIds: The parameter contains a list of unique identifiers representing the schools for which the conversations count is calculated. Multiple school IDs can be provided to consider conversations across multiple schools.</param>
    /// <returns>Returns the count of conversations for a specified user.</returns>
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
    /// Retrieve paginated conversations based on specified criteria and user ID, taking into account whether the request is from an intranet or LMS user.
    /// </summary>
    /// <param name="listingSelector">An object of type IListingSelector<IConversationListing> representing the criteria for selecting conversations.</param>
    /// <param name="userId">An integer representing the unique identifier of the user for whom conversations are being retrieved.</param>
    /// <param name="schoolIds">A list of integers containing the unique identifiers of schools for which conversations are being retrieved.</param>
    /// <returns>Returns paginated conversations based on specified criteria and user ID.</returns>
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

    [HttpGet]
    [Route("{conversationId:int}")]
    [SwaggerOperation("GetConversationGeneralInfos")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(ConversationResponseModel))]
    [ApiVersion("1")]

    /// <summary>
    /// Retrieve general information for a conversation involving multiple schools asynchronously.
    /// </summary>
    /// <param name="conversationId">The identifier of the conversation for which general information is to be retrieved.</param>
    /// <param name="userId">The identifier of the user requesting the general information.</param>
    /// <param name="schoolId">The identifier of the school to which the conversation belongs. This parameter is optional as it may not be applicable for conversations involving multiple schools.</param>
    /// <returns>Returns general information for a conversation involving multiple schools asynchronously.</returns>
    public async Task<ConversationResponseModel> GetConversationGeneralInfosAsync(int conversationId, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] int? schoolId)
    {
        var schoolIds = schoolId != null ? new List<int> { (int)schoolId } : new List<int>();

        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        var conversationAto = await _conversationService.GetConversationByIdWithChecksAsync(conversationId, userId, schoolIds, isRequestFromIntranet)!;

        return conversationAto.ToResponseModel(userId);
    }

    [HttpPost]
    [Route("{conversationId:int}/messages/get")]
    [SwaggerOperation("SearchPaginatedMessagesByConversation")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(MessageResponseModel))]
    [ApiVersion("1")]

    /// <summary>
    /// Retrieve paginated conversation messages asynchronously based on the specified page number and page size, ensuring the page number and page size are valid.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation for which messages are to be retrieved. It should be an integer.</param>
    /// <param name="listingSelector">The selector object that specifies the criteria for listing conversations. It should implement the IListingSelector interface with a type of IConversationListing.</param>
    /// <param name="userId">The ID of the user for whom the conversation messages are being retrieved. It should be an integer.</param>
    /// <param name="schoolIds">A list of IDs representing the schools for which messages are to be retrieved. Each ID in the list should be an integer.</param>
    /// <returns>Returns paginated conversation messages asynchronously.</returns>
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
    /// Update the 'isArchived' status for multiple conversations by user ID.
    /// </summary>
    /// <param name="body">The model representing the request body for patching multiple conversations in the archive. It contains information necessary to update the 'isArchived' status.</param>
    /// <param name="userId">The ID of the user for whom the conversations need to be updated. It is an integer value.</param>
    /// <param name="schoolIds">A list of integer values representing the IDs of the schools whose conversations are to be updated in the archive. Multiple school IDs can be provided in the list.</param>
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
    /// Update the status of multiple conversations asynchronously based on the provided IDs, conversation status, user ID, and school ID.
    /// </summary>
    /// <param name="body">The model containing the data to update the status of multiple conversations.</param>
    /// <param name="userId">The ID of the user for whom the conversations' status needs to be updated.</param>
    /// <param name="schoolId">The ID of the school to which the conversations belong and for which the status needs to be updated.</param>
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
    /// Update the read date of a conversation for a specified user and school.
    /// </summary>
    /// <param name="markConversationAsReadOrUnread">The MarkConversationAsReadOrUnreadRequestModel parameter is used to specify whether the conversation should be marked as read or unread.</param>
    /// <param name="userId">The userId parameter represents the unique identifier of the user for whom the read date of the conversation will be updated.</param>
    /// <param name="schoolIds">The schoolIds parameter is a list of integer values representing the identifiers of the schools for which the read date of the conversation will be updated.</param>
    [HttpPatch]
    [HttpCode(HttpStatusCode.NoContent)]
    [Route("reading-status")]
    [SwaggerResponse((int)HttpStatusCode.NoContent)]
    [ApiVersion("1")]
    public async Task ChangeReadedDateSenderAsync([FromBody] MarkConversationAsReadOrUnreadRequestModel markConversationAsReadOrUnread, [FromQuery(Name = "user-id")] int userId, [FromQuery(Name = "school-id")] List<int> schoolIds)
    {
        await _conversationService.ChangeReadedDateAsync(markConversationAsReadOrUnread.Ids, markConversationAsReadOrUnread.MarkAsRead, userId, schoolIds.ToArray());
    }

    [HttpPost]
    [Route("{id}/correspondants")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(ConversationCorrespondantResponseModel[]))]
    [SwaggerOperation("AddRecipients")]
    [ApiVersion("1")]

    /// <summary>
    /// Add recipients to a conversation asynchronously, based on specified conditions and data, and return the added recipients as response models.
    /// </summary>
    /// <param name="newRecipientsUsersIds">The list of new recipient user IDs to be added to the conversation. It should be of type IEnumerable<int>.</param>
    /// <param name="userId">The ID of the user initiating the addition of recipients to the conversation. It should be of type int.</param>
    /// <param name="schoolIds">The list of school IDs associated with the recipients. It should be of type List<int>.</param>
    /// <param name="id">The unique identifier for the conversation to which recipients are being added. It should be of type int.</param>
    /// <returns>Returns added recipients as response models asynchronously.</returns>
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

    [HttpDelete]
    [HttpCode(HttpStatusCode.NoContent)]
    [Route("{id}/correspondants")]
    [SwaggerResponse((int)HttpStatusCode.NoContent)]
    [SwaggerOperation("RemoveRecipients")]
    [ApiVersion("1")]

    /// <summary>
    /// Remove recipients from a conversation asynchronously, taking into account the source of the request.
    /// </summary>
    /// <param name="recipientsUsersIds">The list of user IDs representing the recipients to be removed from the conversation.</param>
    /// <param name="userId">The ID of the user initiating the removal of recipients from the conversation.</param>
    /// <param name="schoolIds">The list of school IDs associated with the recipients to be removed.</param>
    /// <param name="id">The unique identifier of the conversation from which recipients are being removed.</param>
    public async Task RemoveRecipientsAsync(
        [FromBody] IEnumerable<int> recipientsUsersIds,
        [FromQuery(Name = "user-id")] int userId,
        [FromQuery(Name = "school-id")] List<int> schoolIds,
        [FromRoute] int id)
    {
        var isRequestFromIntranet = !User.StudiIdentity().IsLmsUser;

        await _conversationService.RemoveRecipientsAsync(id, userId, schoolIds, recipientsUsersIds, isRequestFromIntranet);
    }

    [HttpPost]
    [Route("{conversationId:int}/messages")]
    [SwaggerOperation("AddMessageToExistingConversation")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(MessageResponseModel))]
    [ApiVersion("1")]

    /// <summary>
    /// Add a new message to an existing conversation asynchronously.
    /// </summary>
    /// <param name="conversationId">The ID of the conversation to which the new message will be added.</param>
    /// <param name="newMessage">The model representing the new message that will be added to the conversation.</param>
    /// <param name="userId">The ID of the user who is adding the new message to the conversation.</param>
    /// <param name="schoolId">The ID of the school to which the conversation belongs.</param>
    /// <param name="enableNotification">A boolean flag indicating whether to send a notification for the new message. Default value is true.</param>
    /// <returns>Returns a Task representing the result of adding a new message asynchronously.</returns>
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