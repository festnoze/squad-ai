using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileQueryingService
    {

    /// <summary>
    /// Check the payment reliability status for a specified user.
    /// </summary>
    /// <param name="userId">The identifier of the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns a Task indicating the payment reliability status of the specified user.</returns>

        Task<string> GetPaymentReliabilityAsync(int userId);

    /// <summary>
    /// Retrieve user details including personal information, ensuring validity through data validation checks.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns user profile and personal details as a validated user object.</returns>

        Task<UserModel> GetUserWithPersonalInfosAsync(int userId);

    /// <summary>
    /// Retrieve basic information for a specified user after confirming their existence.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user is linked.</param>
    /// <param name="loadSchoolOptions">Optional parameter indicating whether to load additional school options. Default is false.</param>
    /// <returns>Returns a user's basic profile information.</returns>

        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false);

    /// <summary>
    /// Retrieve user public information and related school options for a specified user. Check for the existence of user data and handle possible null values.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and corresponding civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user. This helps in retrieving specific details related to the user's affiliation with the school.</param>
    /// <returns>Returns the user's public profile and associated school details.</returns>

        Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve school options associated with a specific user and school, validating the data and returning a structured model.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and corresponding civility details need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user profile information and corresponding civility details.</param>
    /// <returns>Returns a list of validated school options for the specified user and school.</returns>

        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId);

    /// <summary>
    /// Retrieve the professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the profile information and corresponding civility details are to be retrieved.</param>
    /// <returns>Returns a list of professional experiences for the specified user.</returns>

        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId);

    /// <summary>
    /// Retrieve the review date of a user's profile based on a specific user ID.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose profile information and corresponding civility details are being retrieved.</param>
    /// <returns>Returns the review date of a user's profile.</returns>

        Task<DateTime?> GetUserProfileReviewDateAsync(int userId);

    /// <summary>
    /// Retrieve the most recent study information for a specified user.
    /// </summary>
    /// <param name="userId">The user ID for which the profile information and corresponding civility details are to be retrieved.</param>
    /// <returns>Returns the most recent study information for the specified user.</returns>

        Task<StudyModel?> GetUserLastStudyInfosAsync(int userId);

    /// <summary>
    /// Retrieve a list of contract types related to professional experiences.
    /// </summary>
    /// <returns>Returns a task containing a list of contract type strings.</returns>

        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync();

    /// <summary>
    /// Retrieve trainings associated with a specified user and school, ensuring data validity and returning an existing list of training models.
    /// </summary>
    /// <param name="userId">The unique identifier for a user. This ID is used to retrieve the user profile information along with the corresponding civility details.</param>
    /// <param name="schoolId">The unique identifier for a school. This ID helps to filter and contextualize the user's profile information within the specific school context.</param>
    /// <returns>Returns a list of training models for a specified user and school.</returns>
        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve user notifications settings for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and corresponding civility details are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to filter the user's profile information and corresponding civility details.</param>
    /// <returns>Returns user notification settings for the specified user and school.</returns>

        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the time zone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details need to be retrieved.</param>
    /// <returns>Returns the time zone information of the specified user.</returns>

        Task<string> GetUserTimeZoneAsync(int userId);

    /// <summary>
    /// Retrieve configuration information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user. This helps in retrieving school-specific information if needed.</param>
    /// <returns>Returns configuration details for a specified user and associated school.</returns>

        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the last session information for a specified user and school.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the profile information and civility details are to be retrieved. This is a required parameter for identifying the user in the GetLastSessionInfosAsync method.</param>
    /// <param name="schoolId">The ID of the school associated with the user. This parameter helps to retrieve the specific user profile information and civility details in the context of the specified school in the GetLastSessionInfosAsync method.</param>
    /// <returns>Returns the last session information of a given user in a specified school.</returns>

        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are being retrieved.</param>
    /// <returns>Returns the user's first connection date asynchronously.</returns>

        Task<DateTime?> GetUserFirstConnectionDateAsync(int userId);

    /// <summary>
    /// Retrieve the avatar URL for a specified user or return the default avatar URL if none is available.
    /// </summary>
    /// <param name="userId">The identifier for the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns the avatar URL for the specified user or a default if unavailable.</returns>

        Task<string> GetAvatarUrlAsync(int userId);

    /// <summary>
    /// Check if a user exists by their email address.
    /// </summary>
    /// <param name="email">The email address associated with the user profile to be retrieved. This parameter is used to locate and return the user's profile information and corresponding civility details.</param>
    /// <returns>Returns a boolean indicating whether a user exists with the given email address.</returns>

        Task<bool> ExistUserByEmailAsync(string email);

    /// <summary>
    /// Check if a user exists by their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudonym or username of the user whose profile information and civility details are to be retrieved.</param>
    /// <returns>Returns whether a user exists by their pseudonym.</returns>

        Task<bool> ExistUserByPseudoAsync(string pseudo);

    /// <summary>
    /// Generate a pseudonym for a user based on their given first name and last name.
    /// </summary>
    /// <param name="firstName">The first name of the user to retrieve profile information for.</param>
    /// <param name="lastName">The last name of the user to retrieve profile information for.</param>
    /// <returns>Returns a pseudonym based on the user's first and last names.</returns>

        Task<string> GeneratePseudoAsync(string firstName, string lastName);

    /// <summary>
    /// Retrieve the total number of user profiles based on specified filtering conditions.
    /// </summary>
    /// <param name="filtersCompositions">An optional collection of filter compositions that determine which profiles to count. Each filter composition can provide specific criteria for filtering the profiles.</param>
    /// <returns>Returns the total count of user profiles matching the specified filters.</returns>

        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null);

    /// <summary>
    /// Retrieve a list of user profiles based on specified filters and sorting parameters, including civility information.
    /// </summary>
    /// <param name="skip">The number of records to skip before starting to return results.</param>
    /// <param name="take">The number of records to return.</param>
    /// <param name="filtersCompositions">A collection of filters applied to the results. Null if no filters are specified.</param>
    /// <param name="sort">The sorting criteria for the results. Null if no specific sorting is required.</param>
    /// <returns>Returns a list of filtered and sorted user profiles.</returns>

        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null);

    /// <summary>
    /// Retrieve user profile information and corresponding civility details based on the provided user ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information and civility details are being retrieved.</param>
    /// <returns>Returns user profile and civility details for the specified user ID.</returns>

        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}