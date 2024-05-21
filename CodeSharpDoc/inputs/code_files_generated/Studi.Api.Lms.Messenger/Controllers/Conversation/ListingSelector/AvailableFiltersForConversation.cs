using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.Messenger.Shared.ConversationListing;
using Studi.Api.Lms.Messenger.Shared.ConversationListing.AllowedValuesByFilter;
using Studi.Api.Core.ListingSelector.Filtering.AvailableFilters;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems.Implementation;
using Studi.Api.Core.ListingSelector.Filtering.Operators;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation.ListingSelector
{
    /// <summary>
    /// Provides available filters for the Conversation listing.
    /// </summary>
    [ScopedService(typeof(IAvailableFilters<IConversationListing>))]
    public class AvailableFiltersForConversation : AvailableFilters<IConversationListing>
    {
        /// <summary>
        /// Filter for messaging type.
        /// </summary>
        public IFilterItem<IConversationListing> MessagingType = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Equal, Enum.GetNames<ConversationTypeFilterValueEnum>());

        /// <summary>
        /// Filter for archived conversations.
        /// </summary>
        public IFilterItem<IConversationListing> IsArchived = new FilterItem<IConversationListing, bool>(FilterOperatorEnum.Equal);

        /// <summary>
        /// Filter for conversation status.
        /// </summary>
        public IFilterItem<IConversationListing> ConversationStatus = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Equal, Enum.GetNames<ConversationFilterOnConversationStatusValueEnum>());

        /// <summary>
        /// Filter for conversation origin.
        /// </summary>
        public IFilterItem<IConversationListing> ConversationOrigin = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Equal, Enum.GetNames<ConversationFilterOnOriginValueEnum>());

        /// <summary>
        /// Filter for corresponding user ID.
        /// </summary>
        public IFilterItem<IConversationListing> ContainsCorrespondantUserId = new FilterItem<IConversationListing, int>(FilterOperatorEnum.Equal);

        /// <summary>
        /// Filter for limiting to audience school ID.
        /// </summary>
        public IFilterItem<IConversationListing> LimitToAudienceSchoolId = new FilterItem<IConversationListing, int?>(FilterOperatorEnum.None);

        /// <summary>
        /// Filter for text search on object.
        /// </summary>
        public IFilterItem<IConversationListing> TextSearchOnObject = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Contains);

        /// <summary>
        /// Filter for conversation origin sender.
        /// </summary>
        public IFilterItem<IConversationListing> SenderCorrespondantInUserIdsList = new FilterItem<IConversationListing, int[]>(FilterOperatorEnum.Contains);

        /// <summary>
        /// Filter for compared with date created
        /// </summary>
        public IFilterItem<IConversationListing> DateCreate = new FilterItem<IConversationListing, DateTime>(new List<FilterOperatorEnum>() { FilterOperatorEnum.LessThanOrEqual, FilterOperatorEnum.GreaterThanOrEqual });

        /// <summary>
        /// Filter for with message sender user list.
        /// </summary>
        public IFilterItem<IConversationListing> MessageSenderIncludeInUserIdsList = new FilterItem<IConversationListing, int[]>(new List<FilterOperatorEnum>() { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        /// <summary>
        /// Filter for only not deleted conversation.
        /// </summary>
        public IFilterItem<IConversationListing> OnlyNotDeleted = new FilterItem<IConversationListing, bool>(FilterOperatorEnum.Equal);


        /// <summary>
        /// Initializes a new instance of the <see cref="AvailableFiltersForConversation"/> class.
        /// </summary>
        public AvailableFiltersForConversation() : base(typeof(ConversationFiltersEnum))
        { }
    }
}
