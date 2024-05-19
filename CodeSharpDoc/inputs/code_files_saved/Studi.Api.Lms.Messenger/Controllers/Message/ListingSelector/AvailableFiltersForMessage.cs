using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Core.ListingSelector.Filtering.AvailableFilters;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems.Implementation;
using Studi.Api.Core.ListingSelector.Filtering.Operators;
using Studi.Api.Lms.Messenger.Shared.MessageListing;

namespace Studi.Api.Lms.Messenger.Controllers.Message.ListingSelector
{
    /// <summary>
    /// Provides available filters for the Message listing.
    /// </summary>
    [ScopedService(typeof(IAvailableFilters<IMessageListing>))]
    public class AvailableFiltersForMessage : AvailableFilters<IMessageListing>
    {
        /// <summary>
        /// Filter for conversation origin sender.
        /// </summary>
        public IFilterItem<IMessageListing> SenderCorrespondantInUserIdsList = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        /// <summary>
        /// Filter for conversation corresponding user ID list .
        /// </summary>
        public IFilterItem<IMessageListing> HasCorrespondantIncludedInUserIdsList = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        /// <summary>
        /// Filter for message origin sender.
        /// </summary>
        public IFilterItem<IMessageListing> MessageSenderIncludeInUserIdsList = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        /// <summary>
        /// Filter for limiting to audience school ID.
        /// </summary>
        public IFilterItem<IMessageListing> AudienceSchoolIds = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        /// <summary>
        /// Filter for only not deleted message.
        /// </summary>
        public IFilterItem<IMessageListing> OnlyNotDeleted = new FilterItem<IMessageListing, bool>(FilterOperatorEnum.Equal);

        /// <summary>
        /// Filter for only not deleted conversation.
        /// </summary>
        public IFilterItem<IMessageListing> OnlyConversationNotDeleted = new FilterItem<IMessageListing, bool>(FilterOperatorEnum.Equal);

        /// <summary>
        /// Filter for compared with date created
        /// </summary>
        public IFilterItem<IMessageListing> DateCreate = new FilterItem<IMessageListing, DateTime>(new List<FilterOperatorEnum>() { FilterOperatorEnum.LessThanOrEqual, FilterOperatorEnum.GreaterThanOrEqual });

        /// <summary>
        /// Initializes a new instance of the <see cref="AvailableFiltersForMessage"/> class.
        /// Filter for text search on object.
        /// </summary>
        public IFilterItem<IMessageListing> MessageContent = new FilterItem<IMessageListing, string>(new[] { FilterOperatorEnum.Equal, FilterOperatorEnum.StartsWith, FilterOperatorEnum.Contains, FilterOperatorEnum.EndsWith });
    }
}
