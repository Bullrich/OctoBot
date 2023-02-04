#  This file is part of OctoBot (https://github.com/Drakkar-Software/OctoBot)
#  Copyright (c) 2023 Drakkar-Software, All rights reserved.
#
#  OctoBot is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either
#  version 3.0 of the License, or (at your option) any later version.
#
#  OctoBot is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  General Public License for more details.
#
#  You should have received a copy of the GNU General Public
#  License along with OctoBot. If not, see <https://www.gnu.org/licenses/>.
import octobot.constants as constants
import octobot_commons.constants as common_constants
import octobot_commons.logging as logging
import octobot_commons.time_frame_manager as time_frame_manager
import octobot_tentacles_manager.api as tentacles_manager_api
import octobot_evaluators.api as evaluators_api


def _apply_exchanges_limits(dict_config, logger, limit):
    exchanges = [
        f"{exchange}[{config.get(common_constants.CONFIG_EXCHANGE_TYPE, common_constants.CONFIG_EXCHANGE_SPOT)}]"
        for exchange, config in dict_config[common_constants.CONFIG_EXCHANGES].items()
        if config.get(common_constants.CONFIG_ENABLED_OPTION, True)
    ]
    if len(exchanges) > limit:
        enabled_exchanges = []
        for exchange, config in dict_config[common_constants.CONFIG_EXCHANGES].items():
            if config.get(common_constants.CONFIG_ENABLED_OPTION, True):
                if len(enabled_exchanges) < limit:
                    enabled_exchanges.append(exchange)
                else:
                    config[common_constants.CONFIG_ENABLED_OPTION] = False
                    logger.error("Disabled " + exchange)
        return f"Reached maximum allowed simultaneous exchanges for this plan, maximum is {limit}. " \
               f"Your OctoBot will trade on the following exchanges: {', '.join(enabled_exchanges)}"
    return ""


def _apply_symbols_limits(dict_config, logger, limit):
    enabled_symbols = []
    has_disabled_symbols = False
    message = ""
    for currency, crypto_currency_data in dict_config[common_constants.CONFIG_CRYPTO_CURRENCIES].items():
        if crypto_currency_data.get(common_constants.CONFIG_ENABLED_OPTION, True):
            if len(enabled_symbols) >= limit:
                crypto_currency_data[common_constants.CONFIG_ENABLED_OPTION] = False
                logger.error(f"Disabled all {currency} trading pairs")
                has_disabled_symbols = True
                continue
            updated_symbols = []
            for symbol in crypto_currency_data[common_constants.CONFIG_CRYPTO_PAIRS]:
                if symbol == common_constants.CONFIG_SYMBOLS_WILDCARD[0] \
                        or symbol == common_constants.CONFIG_SYMBOLS_WILDCARD:
                    crypto_currency_data[common_constants.CONFIG_ENABLED_OPTION] = False
                    message = f"Disabled wildcard symbol for {currency}. "
                    has_disabled_symbols = True
                    break
                else:
                    if len(enabled_symbols) < limit:
                        enabled_symbols.append(symbol)
                        updated_symbols.append(symbol)
                    else:
                        has_disabled_symbols = True
                        logger.error(f"Disabled {symbol} trading pair from {currency}")
            crypto_currency_data[common_constants.CONFIG_CRYPTO_PAIRS] = updated_symbols
    if has_disabled_symbols:
        return f"{message}Reached maximum allowed simultaneous trading pairs for this plan, maximum is {limit}. " \
               f"Your OctoBot will trade following pairs: {', '.join(enabled_symbols)}."
    return message


def _apply_time_frames_limits(full_config, logger, limit):
    tentacles_setup_config = tentacles_manager_api.get_tentacles_setup_config(full_config.get_tentacles_config_path())
    has_disabled_time_frames = False
    all_enabled_time_frames = []
    # patch time frames config
    for strategy_class in evaluators_api.get_activated_strategies_classes(tentacles_setup_config):
        config_time_frames = evaluators_api.get_time_frames_from_strategy(
            strategy_class, full_config.config, tentacles_setup_config
        )
        combined_time_frames = set(all_enabled_time_frames + config_time_frames)
        if len(combined_time_frames) < limit:
            all_enabled_time_frames = time_frame_manager.sort_time_frames(list(combined_time_frames))
        elif len(combined_time_frames) > limit:
            has_disabled_time_frames = True
            if len(all_enabled_time_frames) == limit:
                # no timeframe to add
                pass
            else:
                # disable shortest timeframes first
                missing_tf = time_frame_manager.sort_time_frames([
                    tf
                    for tf in config_time_frames
                    if tf not in all_enabled_time_frames
                ])
                added_time_frames = missing_tf[limit-len(all_enabled_time_frames):]
                all_enabled_time_frames = time_frame_manager.sort_time_frames(
                    list(all_enabled_time_frames) + added_time_frames
                )
        else:
            all_enabled_time_frames = list(combined_time_frames)
        if has_disabled_time_frames:
            should_update_config = False
            strategy_enabled_time_frames = [
                tf
                for tf in config_time_frames
                if tf in all_enabled_time_frames
            ]
            for time_frame in config_time_frames:
                if time_frame not in strategy_enabled_time_frames:
                    should_update_config = True
                    logger.error(f"Disabled {time_frame.value} time frame for {strategy_class.get_name()}")
            if should_update_config:
                evaluators_api.update_time_frames_config(
                    strategy_class, tentacles_setup_config, strategy_enabled_time_frames
                )
    if has_disabled_time_frames:
        return f"Reached maximum allowed simultaneous time frames for this plan, maximum is {limit}. " \
           f"Your OctoBot will trade using following time frames: " \
               f"{', '.join([tf.value for tf in all_enabled_time_frames])}."
    return ""


def apply_config_limits(configuration) -> list:
    logger = logging.get_logger("ConfigurationLimits")
    limit_warning_messages = []
    try:
        if constants.MAX_ALLOWED_EXCHANGES != constants.UNLIMITED_ALLOWED:
            if message := _apply_exchanges_limits(configuration.config, logger, constants.MAX_ALLOWED_EXCHANGES):
                limit_warning_messages.append(message)
        if constants.MAX_ALLOWED_SYMBOLS != constants.UNLIMITED_ALLOWED:
            if message := _apply_symbols_limits(configuration.config, logger, constants.MAX_ALLOWED_SYMBOLS):
                limit_warning_messages.append(message)
        if constants.MAX_ALLOWED_TIME_FRAMES != constants.UNLIMITED_ALLOWED:
            if message := _apply_time_frames_limits(configuration, logger, constants.MAX_ALLOWED_TIME_FRAMES):
                limit_warning_messages.append(message)
    except Exception as err:
        logger.exception(err, True, f"Error when applying limits: {err}")
    if limit_warning_messages:
        for message in limit_warning_messages:
            logger.error(message)
    return limit_warning_messages
