using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Core.ListingSelector.Sorting.SortItems;
using Studi.Api.Core.ListingSelector.Sorting.AvailableSortings;
using Studi.Api.Lms.Messenger.Shared.ConversationListing;
using Studi.Api.Core.ListingSelector.Sorting;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation.ListingSelector
{
    /// <summary>
    /// Provides available sorting options for the Conversation listing.
    /// </summary>
    [ScopedService(typeof(IAvailableSortings<IConversationListing>))]
    public class AvailableSortingsForConversation : AvailableSortings<IConversationListing>
    {
        /// <summary>
        /// Sorts conversations by date in ascending or descending order.
        /// </summary>
        public ISortItem<IConversationListing> Date = new SortItem<IConversationListing>(SortDirectionEnum.Asc, SortDirectionEnum.Desc);
    }
}
