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
    /// Verify the reliability of a user's payment status by checking for a non-negative, non-zero user ID and querying the user repository.
    /// </summary>
    /// <param name="userId">The unique identifier representing the user whose profile and civility information are being retrieved.</param>
    /// <returns>Returns a task with the user's payment reliability status.</returns>

        Task<string> GetPaymentReliabilityAsync(int userId);

    /// <summary>
    /// Retrieve personal information for a specified user while ensuring the data is not null.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile and civility information are being retrieved. This should be an integer value.</param>
    /// <returns>Returns a user object containing personal and civility information.</returns>

        Task<UserModel> GetUserWithPersonalInfosAsync(int userId);

    /// <summary>
    /// Retrieve the basic information of a specified user while checking for null and handling exceptions if the user does not exist.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile is to be retrieved.</param>
    /// <param name="schoolId">The ID of the school to associate with the user’s profile.</param>
    /// <param name="loadSchoolOptions">A flag indicating whether to load additional school options. Default is false.</param>
    /// <returns>Returns basic user information asynchronously.</returns>

        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false);

    /// <summary>
    /// Retrieve public information for a specified user and their school options.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile needs to be retrieved.</param>
    /// <param name="schoolId">The identifier of the school to which the user belongs. It's used to retrieve relevant public information.</param>
    /// <returns>Returns a user’s public information and school options asynchronously.</returns>

        Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve school options available for a specified user, ensuring the data exists and is valid before returning it as an existing user school options model.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns user-specific school options model.</returns>

        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId);

    /// <summary>
    /// Retrieve the professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose professional experiences are being retrieved.</param>
    /// <returns>Returns a list of the user's professional experiences.</returns>

        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId);

    /// <summary>
    /// Retrieve the review date of a user's profile based on the specified user ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is being retrieved. This is an integer value.</param>
    /// <returns>Returns the profile review date as a Task<DateTime> instance.</returns>

        Task<DateTime?> GetUserProfileReviewDateAsync(int userId);

    /// <summary>
    /// Retrieve the last study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civil information is being retrieved.</param>
    /// <returns>Returns the latest study details for the specified user.</returns>

        Task<StudyModel?> GetUserLastStudyInfosAsync(int userId);

    /// <summary>
    /// Retrieve a list of contract types relevant to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types.</returns>

        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync();

    /// <summary>
    /// Retrieve the trainings for a specified user within a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school which will be used to fetch the user's profile and civility information.</param>
    /// <returns>Returns a list of the user's training sessions within the specified school.</returns>
        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve notification settings for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to filter the user's notifications.</param>
    /// <returns>Returns the user's notification settings filtered by school.</returns>

        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the time zone for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile and civility information is being retrieved.</param>
    /// <returns>Returns the user's time zone identifier.</returns>

        Task<string> GetUserTimeZoneAsync(int userId);

    /// <summary>
    /// Retrieve user configuration information based on specified user and school identifiers.
    /// </summary>
    /// <param name="userId">Represents the unique identifier for the user whose profile information is being retrieved. This parameter is critical to identify and fetch the correct user data.</param>
    /// <param name="schoolId">Denotes the unique identifier of the school associated with the user. This parameter is used to filter and fetch user information specific to a particular school entity.</param>
    /// <returns>Returns user configuration information as an asynchronous task.</returns>

        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the last session information for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user's profile.</param>
    /// <returns>Returns the last session details for a given user in a specific school.</returns>

        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Get the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile and civility information is to be retrieved.</param>
    /// <returns>Returns the first connection date of the specified user.</returns>

        Task<DateTime?> GetUserFirstConnectionDateAsync(int userId);

    /// <summary>
    /// Retrieve the avatar URL for a specified user, returning a default URL if none is found.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile and civility information are being retrieved.</param>
    /// <returns>Returns the user's avatar URL or a default URL if unavailable.</returns>

        Task<string> GetAvatarUrlAsync(int userId);

    /// <summary>
    /// Check if a user exists by a specified email.
    /// </summary>
    /// <param name="email">The email address used to identify and retrieve the user's profile and civility information.</param>
    /// <returns>Returns true if the user exists; otherwise, false.</returns>

        Task<bool> ExistUserByEmailAsync(string email);

    /// <summary>
    /// Check for the existence of a user based on a provided pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudo or nickname of the user whose profile is being retrieved. This parameter is critical in identifying the specific user in the system.</param>
    /// <returns>Returns a Task<bool> indicating if the user exists by the given pseudonym.</returns>

        Task<bool> ExistUserByPseudoAsync(string pseudo);

    /// <summary>
    /// Generate a pseudonym for a user based on their first name and last name.
    /// </summary>
    /// <param name="firstName">The first name of the user whose profile is being retrieved.</param>
    /// <param name="lastName">The last name of the user whose profile is being retrieved.</param>
    /// <returns>Returns a pseudonym generated from the user's first and last name.</returns>

        Task<string> GeneratePseudoAsync(string firstName, string lastName);

    /// <summary>
    /// Count the total number of user profiles based on specified filtering criteria.
    /// </summary>
    /// <param name="filtersCompositions">Optional. A collection of filters composed using the IFiltersComposition interface for filtering the profiles. This parameter can be null.</param>
    /// <returns>Returns the total count of user profiles matching the specified filters.</returns>

        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null);

    /// <summary>
    /// Retrieve user profiles based on specified filters and sorting, then map the results with corresponding civilities.
    /// </summary>
    /// <param name="skip">The number of items to skip before starting to collect the result set. Useful for pagination.</param>
    /// <param name="take">The number of items to take for the result set. Defines the size of the result.</param>
    /// <param name="filtersCompositions">A collection of filters to apply to the result set, allowing for complex querying. Can be null.</param>
    /// <param name="sort">Defines the sorting criteria for the result set. Can be null.</param>
    /// <returns>Returns a list of user profiles with applied filters and sorting.</returns>

        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null);

    /// <summary>
    /// Retrieve a user's profile along with their civility information, if available.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is being retrieved.</param>
    /// <returns>Returns a user's profile and civility information.</returns>

        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}