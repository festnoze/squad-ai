using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Core.ListingSelector.Filtering.AvailableFilters;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems;
using Studi.Api.Core.ListingSelector.Filtering.FilterItems.Implementation;
using Studi.Api.Core.ListingSelector.Filtering.Operators;
using Studi.Api.Lms.Messenger.Shared.MessageListing;

namespace Studi.Api.Lms.Messenger.Controllers.Message.ListingSelector
{
    [ScopedService(typeof(IAvailableFilters<IMessageListing>))]
    public class AvailableFiltersForMessage : AvailableFilters<IMessageListing>
    {
        public IFilterItem<IMessageListing> SenderCorrespondantInUserIdsList = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        public IFilterItem<IMessageListing> HasCorrespondantIncludedInUserIdsList = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        public IFilterItem<IMessageListing> MessageSenderIncludeInUserIdsList = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        public IFilterItem<IMessageListing> AudienceSchoolIds = new FilterItem<IMessageListing, int[]>(new FilterOperatorEnum[] { FilterOperatorEnum.Contains, FilterOperatorEnum.NotContain });

        public IFilterItem<IMessageListing> OnlyNotDeleted = new FilterItem<IMessageListing, bool>(FilterOperatorEnum.Equal);

        public IFilterItem<IMessageListing> OnlyConversationNotDeleted = new FilterItem<IMessageListing, bool>(FilterOperatorEnum.Equal);

        public IFilterItem<IMessageListing> DateCreate = new FilterItem<IMessageListing, DateTime>(new List<FilterOperatorEnum>() { FilterOperatorEnum.LessThanOrEqual, FilterOperatorEnum.GreaterThanOrEqual });

        public IFilterItem<IMessageListing> MessageContent = new FilterItem<IMessageListing, string>(new[] { FilterOperatorEnum.Equal, FilterOperatorEnum.StartsWith, FilterOperatorEnum.Contains, FilterOperatorEnum.EndsWith });
    }
}