# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from warehouse.utils.user_agents import should_show_share_image


def test_shows_share_image_for_social_networks() -> None:
    # https://developer.x.com/en/docs/x-for-websites/cards/guides/troubleshooting-cards#validate_twitterbot
    assert should_show_share_image("Twitterbot/1.0") is True
    # https://developers.facebook.com/docs/sharing/webmasters/web-crawlers
    assert (
        should_show_share_image(
            "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
        )
        is True
    )
    assert should_show_share_image("facebookexternalhit/1.1") is True
    assert should_show_share_image("facebookcatalog/1.0") is True
    # https://www.linkedin.com/robots.txt
    assert should_show_share_image("LinkedInBot") is True


def test_doesnt_show_share_image_for_slackbot() -> None:
    # https://api.slack.com/robots
    assert (
        should_show_share_image(
            "Slackbot-LinkExpanding 1.0 (+https://api.slack.com/robots)"
        )
        is False
    )
