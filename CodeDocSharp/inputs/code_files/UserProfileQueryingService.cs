namespace Studi.Api.Lms.Application.Services;

using MediatR;
using Studi.Api.Core.Exceptions.ErrorCodesLocalization.Base;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.User.Application.Interfaces;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;
using Studi.Api.Lms.User.Domain.Aggregates.User.Queries;
using Studi.Api.Lms.User.Localization.Error.GeneratedClasses;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Application.Services.CustomWebResource;
using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Lms.User.Application.Decorators;
using Studi.Api.Lms.User.Application.Tools;
using Studi.Api.Lms.User.Application.Mapper;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Application.Services.Civility;
using Studi.Api.Lms.User.Common.RepositoriesInterfaces;

[ScopedService(typeof(IUserProfileQueryingService))]
public class UserProfileQueryingService : IUserProfileQueryingService
{
    private readonly IMediator _mediator;
    private readonly ICustomWebResourceService _customWebResource;
    private readonly ICivilityService _civilityService;
    private readonly IUserRepository _userRepository;


    /// <summary>
    /// Set up dependencies for querying user profiles, ensuring none of the required components are null.
    /// </summary>
    /// <param name="mediator">The IMediator instance to send and publish domain events.</param>
    /// <param name="customWebResource">The ICustomWebResourceService instance to manage custom web resources.</param>
    /// <param name="civilityService">The ICivilityService instance to handle civil-related services.</param>
    /// <param name="userRepository">The IUserRepository instance to interact with the user database.</param>
    public UserProfileQueryingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserRepository userRepository)
    {
        _mediator = mediator ?? throw new ArgumentNullException();
        _customWebResource = customWebResource ?? throw new ArgumentNullException();
        _civilityService = civilityService ?? throw new ArgumentNullException();
        _userRepository = userRepository;
    }


    /// <summary>
    /// Check the payment reliability for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose payment reliability is being checked.</param>
    /// <returns>Returns the reliability score of the specified user's payment history.</returns>
    public async Task<string?> GetPaymentReliabilityAsync(int userId)
    {
        Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Common.UserId.NegativeOrZero);
        return await _userRepository.GetPaymentReliabilityAsync(userId);
    }



    /// <summary>
    /// Retrieve a user's basic information, ensuring the user exists and handling errors if the user is not found.
    /// </summary>
    /// <param name="userId">The unique identifier of the user to retrieve information for. It must be an integer representing the user's ID in the system.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user. It must be an integer representing the school's ID within the system.</param>
    /// <param name="loadSchoolOptions">A boolean flag indicating whether to load additional school options. If set to true, additional school-related information will be retrieved.</param>
    /// <returns>Returns a task with user's basic info or error if not found.</returns>
    public async Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false)
    {
        var user = await _mediator.Send(new UserBaseQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.User.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        var userBasicInfoIto = await _mediator.Send(new UserBasicInfoQuery(userId));
        user!.SetBasicInfoInformations(BasicInfoModel.CreateExisting(userBasicInfoIto!));

        if (loadSchoolOptions)
        {
            var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
            Guard.Against.Null(userSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve a user's public information and associated school options, verifying the user's existence and handling missing data appropriately.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose public information is to be retrieved. This parameter ensures that the system retrieves the correct user's data.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user. This parameter helps in fetching the appropriate school options related to the user.</param>
    /// <returns>Returns a user's verified public info and associated school options.</returns>
    public async Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId)
    {
        var user = await _mediator.Send(new UserPublicInfoQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.PublicInfo.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString()); //TODO Localize

        var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        if (userSchoolOptions != null)
        {
            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));

            var userScoresItos = await _mediator.Send(new UserScoresQuery(userId, schoolId));
            user!.SetUserScoresModel(userScoresItos is null ? null : UserScoresModel.CreateExisting(userScoresItos!));

            var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
            Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);
            user!.SetTrainings(TrainingModel.CreateExistingList(userTrainingsItos!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve the first course registration details for a specified user in a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the first course registration details are being retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school where the user's course registration is being checked.</param>
    /// <returns>Returns the first course registration details for the specified user at the specified school.</returns>
    //[Obsolete("replaced by Trainings")]
    //public async Task<UserModel> GetUserWithCoursesRegistrationsAsync(int userId, int schoolId)
    //{
    //    var user = await _mediator.Send(new UserCoursesRegistrationsQuery(userId, schoolId));
    //    return user.UserCoursesRegistrations.First().ToIto();
    //}


    /// <summary>
    /// Retrieve personal information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose personal information is being retrieved. This should be an integer value.</param>
    /// <returns>Returns user personal information in an asynchronous operation.</returns>
    public async Task<UserModel> GetUserWithPersonalInfosAsync(int userId)
    {
        var userWPersonalInfos = await _mediator.Send(new UserPersonnalInformationsQuery(userId));
        Guard.Against.Null(userWPersonalInfos, ErrorCode.Api.Lms.User.DataValidation.Query.PersonnalInfos.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        return userWPersonalInfos!;
    }


    /// <summary>
    /// Retrieve school options for a specified user and school, ensuring the data exists and returning a correctly formatted model.
    /// </summary>
    /// <param name="userId">The unique identifier for the user for whom the school options are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school whose data is being retrieved for the specified user.</param>
    /// <returns>Returns a formatted model with school options for the specified user and school.</returns>
    public async Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId)
    {
        var userWSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        Guard.Against.Null(userWSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

        return UserSchoolOptionsModel.CreateExisting(userWSchoolOptions!);
    }


    /// <summary>
    /// Retrieve professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom to retrieve professional experiences.</param>
    /// <returns>Returns a list of the user's professional experiences.</returns>
    public async Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId)
    {
        return (await _mediator.Send(new UserProfessionalExperiencesQuery(userId))).ProfessionalExperiences;
    }


    /// <summary>
    /// Retrieve the review date of the user profile for a specified user.
    /// </summary>
    /// <param name="userId">The identifier of the user whose profile review date is to be retrieved.</param>
    /// <returns>Returns the review date of the specified user's profile.</returns>
    public async Task<DateTime?> GetUserProfileReviewDateAsync(int userId)
    {
        return await _mediator.Send(new UserProfileReviewDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">A unique identifier representing the user for whom the latest study information is to be retrieved. This parameter should be an integer.</param>
    /// <returns>Returns the user's latest study information asynchronously.</returns>
    public async Task<StudyModel?> GetUserLastStudyInfosAsync(int userId)
    {
        return await _mediator.Send(new UserLastStudyInfosQuery(userId));
    }


    /// <summary>
    /// Retrieve the list of all contract types for professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types for professional experiences.</returns>
    public async Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync()
    {
        return await _mediator.Send(new AllContractTypesForProfessionalExperiencesQuery());
    }


    /// <summary>
    /// Retrieve the list of training sessions for a specified user from a given school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the training sessions are being retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school from which the training sessions are being retrieved.</param>
    /// <returns>Returns a list of training sessions for a specified user from a given school.</returns>
    public async Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId)
    {
        var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
        Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);

        return TrainingModel.CreateExistingList(userTrainingsItos);
    }


    /// <summary>
    /// Get user notifications based on a specified user ID and school ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose notifications are being retrieved. This parameter is necessary to specify the user in the 'GetUserNotificationsByIdAndSchoolIdAsync' method.</param>
    /// <param name="schoolId">The unique identifier for the school to filter notifications by. This parameter is used alongside 'userId' in the 'GetUserNotificationsByIdAndSchoolIdAsync' method to specify notifications related to a particular school.</param>
    /// <returns>Returns user notifications filtered by user and school ID.</returns>
    public async Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserNotificationsSettingsQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the time zone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose time zone information is being retrieved.</param>
    /// <returns>Returns the user's time zone information.</returns>
    public async Task<string> GetUserTimeZoneAsync(int userId)
    {
        return await _mediator.Send(new UserTimeZoneQuery(userId));
    }


    /// <summary>
    /// Retrieve user configuration information based on specified user and school identifiers.
    /// </summary>
    /// <param name="userId">The identifier of the user whose configuration information is to be retrieved. This is an integer value that uniquely identifies the user in the system.</param>
    /// <param name="schoolId">The identifier of the school associated with the user. This is an integer value that uniquely identifies the school in the system.</param>
    /// <returns>Returns user configuration details for specified user and school.</returns>
    public async Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserConfigInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the last session information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the last session information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <returns>Returns the last session information for a user at a specified school.</returns>
    public async Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserLastSessionInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the first connection date is being retrieved.</param>
    /// <returns>Returns the user's initial connection date asynchronously.</returns>
    public async Task<DateTime?> GetUserFirstConnectionDateAsync(int userId)
    {
        return await _mediator.Send(new UserFirstConnectionDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the URL of a user's avatar, or return a default avatar URL if the user-specific URL is invalid or empty.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose avatar URL is being retrieved.</param>
    /// <returns>Returns the URL of the user's avatar or a default avatar URL.</returns>
    public async Task<string> GetAvatarUrlAsync(int userId)
    {
        var url = await _mediator.Send(new UserAvatarUrlQuery(userId));

        if (!string.IsNullOrEmpty(url) 
            && !string.IsNullOrWhiteSpace(url))
            return url;

        return _customWebResource.DefaultAvatarUrl;
    }


    /// <summary>
    /// Check the existence of a user by their email address.
    /// </summary>
    /// <param name="email">The email address to check for user existence.</param>
    /// <returns>Returns a boolean indicating if the user exists by given email.</returns>
    public async Task<bool> ExistUserByEmailAsync(string email)
    {
        return await _mediator.Send(new UserExistByEmailQuery(email));
    }


    /// <summary>
    /// Check if a user exists based on their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudonym of the user to check for existence.</param>
    /// <returns>Returns a boolean indicating user existence by pseudonym.</returns>
    public async Task<bool> ExistUserByPseudoAsync(string pseudo)
    {
        return await _mediator.Send(new UserExistByPseudoQuery(pseudo));
    }


    /// <summary>
    /// Generate a pseudonym based on the provided first and last name.
    /// </summary>
    /// <param name="firstName">The first name of the individual for whom the pseudonym is being generated.</param>
    /// <param name="lastName">The last name of the individual for whom the pseudonym is being generated.</param>
    /// <returns>Returns a pseudonym based on the first and last name provided.</returns>
    public async Task<string> GeneratePseudoAsync(string firstName, string lastName)
    {
        return await _mediator.Send(new UserGeneratePseudoQuery(firstName, lastName));
    }


    /// <summary>
    /// Retrieve the count of user profiles based on specified filter conditions.
    /// </summary>
    /// <param name="filtersCompositions">An enumerable collection of filter compositions that specify the conditions to count user profiles. Each filter composition contains a set of criteria used to match profiles.</param>
    /// <returns>Returns the number of user profiles matching the specified filter conditions.</returns>
    public async Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);

        return await _mediator.Send(new UserProfilesCountQuery(filtersCompositions));
    }


    /// <summary>
    /// Retrieve user profiles based on specified filters and sort criteria, including civilities mapping.
    /// </summary>
    /// <param name="skip">The number of user profiles to skip. Useful for paging through large sets of data.</param>
    /// <param name="take">The number of user profiles to take. This determines the maximum number of profiles to retrieve in a single operation.</param>
    /// <param name="filtersCompositions">An optional collection of filter compositions used to narrow down the search results based on specific criteria.</param>
    /// <param name="sort">An optional sorting criterion to order the retrieved user profiles by specified properties.</param>
    /// <returns>Returns a task of ordered, filtered user profiles list.
    </returns>
    public async Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);
        PaginationTools.TransformSortFieldName(sort, fieldNameDecorator);

        var data = await _mediator.Send(new UserProfilesQuery(skip, take, filtersCompositions, sort));

        if(!data.Any())
            return Enumerable.Empty<IUserProfileRAto>();

        var civilities = this._civilityService.GetCivilities();
        return data.Select(q => ItoToAtoMapper.ToUserProfileRAto(q, civilities.FirstOrDefault(c => c.Name == q.Civility)?.Id));
    }


    /// <summary>
    /// Retrieve user profile information, optionally including civility data.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information is being retrieved.</param>
    /// <returns>Returns a user's profile information, optionally with civility data.</returns>
    public async Task<IUserProfileRAto> GetUserProfileAsync(int userId)
    {
        var data = await _mediator.Send(new UserProfileQuery(userId));
        var civility = !string.IsNullOrEmpty(data.Civility) ? this._civilityService.GetCivilityByName(data.Civility!) : null;

        return ItoToAtoMapper.ToUserProfileRAto(data, civility?.Id);
    }
}