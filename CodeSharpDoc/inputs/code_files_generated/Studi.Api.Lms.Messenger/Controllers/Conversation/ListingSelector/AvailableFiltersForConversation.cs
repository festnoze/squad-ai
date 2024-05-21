using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.Messenger.Shared.ConversationListing;
using Studi.Api.Lms.Messenger.Shared.ConversationListing.AllowedValuesByFilter;
using Studi.Api.Core.ListingSelector.Filtering.AvailableFilters;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems.Implementation;
using Studi.Api.Core.ListingSelector.Filtering.Operators;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation.ListingSelector
{
    [ScopedService(typeof(IAvailableFilters<IConversationListing>))]
    public class AvailableFiltersForConversation : AvailableFilters<IConversationListing>
    {
        public IFilterItem<IConversationListing> MessagingType = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Equal, Enum.GetNames<ConversationTypeFilterValueEnum>());

        public IFilterItem<IConversationListing> IsArchived = new FilterItem<IConversationListing, bool>(FilterOperatorEnum.Equal);

        public IFilterItem<IConversationListing> ConversationStatus = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Equal, Enum.GetNames<ConversationFilterOnConversationStatusValueEnum>());

        public IFilterItem<IConversationListing> ConversationOrigin = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Equal, Enum.GetNames<ConversationFilterOnOriginValueEnum>());

        public IFilterItem<IConversationListing> ContainsCorrespondantUserId = new FilterItem<IConversationListing, int>(FilterOperatorEnum.Equal);

        public IFilterItem<IConversationListing> LimitToAudienceSchoolId = new FilterItem<IConversationListing, int?>(FilterOperatorEnum.None);

        public IFilterItem<IConversationListing> TextSearchOnObject = new FilterItem<IConversationListing, string>(FilterOperatorEnum.Contains);

        public IFilterItem<IConversationListing> SenderCorrespondantInUserIdsList = new FilterItem<IConversationListing, int[]>(FilterOperatorEnum.Contains);

        public IFilterItem<IConversationListing> DateCreate = new FilterItem<IConversationListing, DateTime>(new List<FilterOperatorEnum>() { FilterOperatorEnum.LessThanOrEqual, FilterOperatorEnum.GreaterThanOrEqual });

        public IFilterItem<IConversationListing> MessageSenderIncludeInUserIdsList = new FilterItem<IConversationListing, int[]>(new List<FilterOperatorEnum>() { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        public IFilterItem<IConversationListing> OnlyNotDeleted = new FilterItem<IConversationListing, bool>(FilterOperatorEnum.Equal);



    /// <summary>
    /// Create available filters for a conversation.
    /// </summary>
    /// <param name="method_name">The name of the existing method (it's always a single word. Also exclude the type of the parameter which may come firstly)</param>
    /// <param name="method_purpose">The purpose of the existing method</param>
    /// <param name="method_context">The context in which the method is used</param>
        public AvailableFiltersForConversation() : base(typeof(ConversationFiltersEnum))
        { }
    }
}