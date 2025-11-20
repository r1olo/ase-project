"""
Repository layer for data access.

Abstracts database operations from business logic.
"""
from typing import Optional, List, Tuple
from sqlalchemy import func, desc, or_
from sqlalchemy.orm import joinedload

from common.extensions import db
from .models import Match, MatchStatus, Round


class MatchRepository:
    """Repository for Match entity operations."""
    
    @staticmethod
    def create(player1_id: int, player2_id: int) -> Match:
        """Create a new match."""
        match = Match(player1_id=player1_id, player2_id=player2_id)
        db.session.add(match)
        return match
    
    @staticmethod
    def find_by_id(match_id: int) -> Optional[Match]:
        """Find a match by ID."""
        return db.session.get(Match, match_id)
    
    @staticmethod
    def find_by_id_with_lock(match_id: int) -> Optional[Match]:
        """Find a match by ID with row-level lock for update."""
        return db.session.scalars(
            db.select(Match).filter_by(id=match_id).with_for_update()
        ).first()
    
    @staticmethod
    def find_by_id_with_rounds(match_id: int) -> Optional[Match]:
        """Find a match by ID with all rounds eagerly loaded."""
        return db.session.scalars(
            db.select(Match)
            .options(joinedload(Match.rounds))
            .filter_by(id=match_id)
        ).first()
    
    @staticmethod
    def find_for_player(
        player_id: int, 
        status: Optional[MatchStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[Match]:
        """
        Find matches for a player with optional status filter.
        Returns matches ordered by most recent first.
        """
        query = db.select(Match).options(
            joinedload(Match.rounds)
        ).filter(
            or_(
                Match.player1_id == player_id,
                Match.player2_id == player_id
            )
        )
        
        if status:
            query = query.filter(Match.status == status)
        
        query = query.order_by(desc(Match.created_at)).limit(limit).offset(offset)
        
        return db.session.scalars(query).unique().all()
    
    @staticmethod
    def count_for_player(player_id: int, status: Optional[MatchStatus] = None) -> int:
        """Count total matches for a player."""
        query = db.select(func.count(Match.id)).filter(
            or_(
                Match.player1_id == player_id,
                Match.player2_id == player_id
            )
        )
        
        if status:
            query = query.filter(Match.status == status)
        
        return db.session.scalar(query)
    
    @staticmethod
    def count_wins_for_player(player_id: int) -> int:
        """Count total wins for a player."""
        return db.session.scalar(
            db.select(func.count(Match.id)).filter(
                Match.winner_id == player_id,
                Match.status == MatchStatus.FINISHED
            )
        )
    
    @staticmethod
    def get_leaderboard_data(limit: int = 100, offset: int = 0) -> List[Tuple[int, int]]:
        """
        Get leaderboard data as list of (player_id, wins).
        Returns aggregated wins per player, ordered by wins descending.
        """
        # Player 1 wins
        player1_wins = db.session.query(
            Match.player1_id.label('player_id'),
            func.count(Match.id).label('wins')
        ).filter(
            Match.winner_id == Match.player1_id,
            Match.status == MatchStatus.FINISHED
        ).group_by(Match.player1_id).subquery()
        
        # Player 2 wins
        player2_wins = db.session.query(
            Match.player2_id.label('player_id'),
            func.count(Match.id).label('wins')
        ).filter(
            Match.winner_id == Match.player2_id,
            Match.status == MatchStatus.FINISHED
        ).group_by(Match.player2_id).subquery()
        
        # Union and aggregate
        leaderboard = db.session.query(
            func.coalesce(player1_wins.c.player_id, player2_wins.c.player_id).label('player_id'),
            (func.coalesce(player1_wins.c.wins, 0) + func.coalesce(player2_wins.c.wins, 0)).label('total_wins')
        ).outerjoin(
            player2_wins, player1_wins.c.player_id == player2_wins.c.player_id
        ).order_by(
            desc('total_wins')
        ).limit(limit).offset(offset).all()
        
        return leaderboard


class RoundRepository:
    """Repository for Round entity operations."""
    
    @staticmethod
    def create(match: Match, round_number: int, category: str) -> Round:
        """Create a new round."""
        round_obj = Round(
            match=match,
            round_number=round_number,
            category=category
        )
        db.session.add(round_obj)
        return round_obj
    
    @staticmethod
    def find_by_match_and_number(match_id: int, round_number: int) -> Optional[Round]:
        """Find a specific round in a match."""
        return db.session.scalars(
            db.select(Round).filter_by(
                match_id=match_id,
                round_number=round_number
            )
        ).first()
    
    @staticmethod
    def find_current_incomplete_round(match_id: int) -> Optional[Round]:
        """Find the current incomplete round for a match (if any)."""
        return db.session.scalars(
            db.select(Round)
            .filter(Round.match_id == match_id)
            .filter(
                or_(
                    Round.player1_card_id.is_(None),
                    Round.player2_card_id.is_(None)
                )
            )
            .order_by(Round.round_number)
        ).first()
    
    @staticmethod
    def find_all_for_match(match_id: int) -> List[Round]:
        """Find all rounds for a match, ordered by round number."""
        return db.session.scalars(
            db.select(Round)
            .filter_by(match_id=match_id)
            .order_by(Round.round_number)
        ).all()
    
    @staticmethod
    def find_completed_rounds(match_id: int) -> List[Round]:
        """Find all completed rounds for a match."""
        return db.session.scalars(
            db.select(Round)
            .filter_by(match_id=match_id)
            .filter(Round.player1_card_id.isnot(None))
            .filter(Round.player2_card_id.isnot(None))
            .order_by(Round.round_number)
        ).all()