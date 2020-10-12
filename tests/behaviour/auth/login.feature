Feature: User can authenticate succesfully
  All things around user authentication & authorization

  Background:
    Given I am a user

  Scenario: Login
    When I go to the login page
    And I enter my credentials
    And I submit the form

    Then I should be on my projects page

  Scenario: Failed login
    When I go to the login page
    And I enter wrong credentials
    And I submit the form

    Then I should be on the login page
    And an invalid password error should be displayed

  Scenario: Logout
    Given I am logged in

    When I open the account menu
    And I click on the logout button

    Then I should be on the home page

    When I go to my projects page
    Then I should be on the login page

    When I open the account menu
    Then there should be a login link
