using Studi.Api.Lms.Messenger.Application.Services.ContactService.Ato;
using Studi.Api.Lms.Messenger.Application.Services.ConversationService.Ato;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Contact.ResponseModel;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.Conversation.ResponseModels;

namespace Studi.Api.Lms.Messenger.Controllers.Conversation.Mapping
{
    internal static class MappingResponseModel
    {
        public static ConversationResponseModel ToResponseModel(this IConversationRAto conversation, int userId)
        {
            return new ConversationResponseModel
            {
                Id = conversation.Id,
                ConversationCorrespondants = conversation.Correspondants.ToResponseModel(userId),
                SchoolId = conversation.AudienceSchoolId,
                Subject = conversation.Subject,
                HasUnreadMessage = conversation.HasUnreadMessage,
                IsReadOnly = conversation.IsReadOnly ?? false,
                ClosingDate = conversation.ClosingDate,
                ReadedDate = conversation.ReadingDate,
                IsArchived = conversation.Correspondants.FirstOrDefault(cor => cor.User.Id == userId)?.IsArchived ?? false,
                ConversationType = (EConversationTypeResponseModel)conversation.Type,
                ConversationStatus = conversation.Status is null ? null : Enum.Parse<EConversationStatusResponseModel>(conversation.Status!.Value.ToString()),
                HasAttachmentOrAudioFile = conversation.HasAttachments || conversation.HasAudioFiles,
                MessagesCount = conversation.MessagesCount,
                DateCreate = conversation.DateCreate,
                DateUpdate = conversation.DateUpdate,
                DateLastMessage = conversation.DateLastMessage
            };
        }

        public static ConversationCorrespondantResponseModel ToResponseModel(this ICorrespondantRAto correspondantRATO, int userId)
        {
            return new ConversationCorrespondantResponseModel()
            {
                Roles = correspondantRATO.Roles.Select(r => (EConversationCorrespondantRoleResponseModel)r),
                ConversationReadingDate = correspondantRATO.ConversationReadingDate,
                User = correspondantRATO.User.ToResponseModel(userId),
            };
        }

        public static IEnumerable<ConversationCorrespondantResponseModel> ToResponseModel(this IEnumerable<ICorrespondantRAto> correspondantsRAto, int userId)
        {
            foreach (var correspondantRAto in correspondantsRAto)
            {
                yield return correspondantRAto.ToResponseModel(userId);
            }
        }

        public static ConversationCorrespondantUserResponseModel ToResponseModel(this ICorrespondantUserRAto correspondantUserRAto, int userId)
        {
            return new ConversationCorrespondantUserResponseModel()
            {
                Id = correspondantUserRAto.Id,
                Pseudo = (correspondantUserRAto.Id == userId) ? "moi" : correspondantUserRAto.Pseudo,
                ProfilePictureUrl = correspondantUserRAto.ProfilePictureUrl,
                Handicaps = correspondantUserRAto.Handicaps.Select(h => h.ToResponseModel()),
                Roles = correspondantUserRAto.Roles.Select(r => r.ToResponseModel()),
                CoursesDelegate = correspondantUserRAto.CoursesDelegate.Select(cd => cd.ToResponseModel())
            };
        }

        public static ConversationCreatedOrNotResponseModel CreateConversationCreatedOrNotResponseModel(IConversationCreatedOrNotAto conversation)
        {
            return new ConversationCreatedOrNotResponseModel
            {
                Id = conversation.Id,
                SchoolId = conversation.SchoolId,
                SenderUserId = conversation.SenderUserId,
                RecipientUsersIds = conversation.RecipientsUsersIds,
            };
        }

        public static UserHandicapResponseModel ToResponseModel(this IUserHandicapRAto handicap)
        {
            return new UserHandicapResponseModel
            {
                Code = handicap.Code,
                Name = handicap.Name,
            };
        }

        public static EUserRoleResponseModel ToResponseModel(this EUserRoleRAto role)
        {
            return (EUserRoleResponseModel)role;
        }

        public static UserCoursesDelegateResponseModel ToResponseModel(this IUserCoursesDelegateRAto userCoursesDelegateRAto)
        {
            return new UserCoursesDelegateResponseModel()
            {
                CourseId = userCoursesDelegateRAto.CourseId,
                CourseName = userCoursesDelegateRAto.CourseName,
                IsSubstitute = userCoursesDelegateRAto.IsSubstitute
            };
        }
    }
}